"""临时：自动发布切换 + pending_delete 异步清理。

设计对齐 docs/rag/文档切分与向量化 §4A.1：
  同 doc 创建时已保证最多一套 canary；发布时仅旧 prod → pending_delete，目标 canary → prod。

正式发布 UI 上线后可下线对应 sys_job。
清理时：Milvus 物理删向量 → segment 写入归档表后主表物理删除。
"""
from __future__ import annotations

import math

from knowledge_common.common.transactional import PropagationBehavior, transactional
from knowledge_common.config.env import EmbeddingConfig, MilvusConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.milvus import DocumentVectorVo, KnowledgeMilvusClient
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.segment_status_enum import ReleaseTag, SegmentArchiveReason
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.dao.document_segment_dao import KnowledgeDocumentSegmentDao
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment


class EmbeddingPublishService:
    """临时发布切换 / pending_delete 清理。"""

    _milvus = KnowledgeMilvusClient()
    _collection = MilvusConfig.document_vector_collection

    @classmethod
    async def auto_promote_completed_canary(cls) -> int:
        """扫描 COMPLETED+canary，自动发布；返回成功文档数。"""
        limit: int = EmbeddingConfig.embedding_publish_promote_batch_size
        tasks: list[KnowledgeDocumentEmbeddingTask] = (
            await KnowledgeDocumentEmbeddingTaskDao.list_completed_canary_candidates(limit)
        )
        if not tasks:
            return 0
        logger.info('[Embedding-publish] 扫描到 {} 个待发布 COMPLETED+canary', len(tasks))
        ok: int = 0
        for task in tasks:
            # 与删除/消费/重试共用 embedding_task 锁，避免 canary 发布中被删
            lock_key: str = LockKey.embedding_task_key(task.task_id)
            async with DistributedLock(lock_key, expire=120, timeout=0) as acquired:
                if not acquired:
                    continue
                try:
                    await cls.promote_task(task.task_id)
                    ok += 1
                    logger.info(
                        '[Embedding-publish] 发布成功: doc_id={}, task_id={}',
                        task.doc_id,
                        task.task_id,
                    )
                except Exception as exc:
                    logger.exception(
                        '[Embedding-publish] 发布失败: doc_id={}, task_id={}, error={}',
                        task.doc_id,
                        task.task_id,
                        exc,
                    )
        return ok

    @classmethod
    async def promote_task(cls, task_id: int) -> None:
        """单任务发布：先切 Milvus 标签（检索时效），再切 MySQL；归档物理删交给 cleanup。"""
        # 0. 查出将被降级的旧 prod task_id（幂等时回落为已 pending_delete）
        demoted_task_ids: list[int] = await cls._list_demoted_prod_task_ids(task_id)
        # 1. 目标向量 Milvus canary → prod
        await cls._mark_milvus_release_tag(task_id, ReleaseTag.PROD.value)
        # 2. 旧 prod 向量 Milvus → pending_delete（检索先摘掉旧流量）
        for demoted_task_id in demoted_task_ids:
            await cls._mark_milvus_release_tag(demoted_task_id, ReleaseTag.PENDING_DELETE.value)
        # 3. MySQL：旧 prod → pending_delete；目标 canary → prod
        await cls._switch_mysql_tags(task_id)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _list_demoted_prod_task_ids(cls, task_id: int) -> list[int]:
        """发布前查出同 doc 将被降级的旧 prod task_id（幂等时回落为已 pending_delete）。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(
            task_id
        )
        if not task:
            raise ServiceException(f'任务不存在: task_id={task_id}')
        if not await KnowledgeDocumentSegmentDao.has_canary_by_doc(task.doc_id):
            return await KnowledgeDocumentSegmentDao.list_task_ids_by_doc_and_tag(
                task.doc_id, ReleaseTag.PENDING_DELETE.value
            )
        return await KnowledgeDocumentSegmentDao.list_task_ids_by_doc_and_tag(
            task.doc_id, ReleaseTag.PROD.value
        )

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _switch_mysql_tags(cls, task_id: int) -> None:
        """旧 prod → pending_delete；目标 canary → prod。同 doc 创建时已保证无第二套 canary。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(
            task_id
        )
        if not task:
            raise ServiceException(f'任务不存在: task_id={task_id}')

        if not await KnowledgeDocumentSegmentDao.has_canary_by_doc(task.doc_id):
            # 幂等：MySQL 已无 canary
            return
        # 1. 旧 prod → pending_delete
        await KnowledgeDocumentSegmentDao.update_release_tag_by_doc_excluding_task(
            task.doc_id,
            exclude_task_id=task_id,
            from_tags=[ReleaseTag.PROD.value],
            to_tag=ReleaseTag.PENDING_DELETE.value,
            update_by='admin',
        )
        # 2. 目标 canary → prod
        promoted: int = await KnowledgeDocumentSegmentDao.update_release_tag_by_task(
            task_id,
            from_tag=ReleaseTag.CANARY.value,
            to_tag=ReleaseTag.PROD.value,
            update_by='admin',
        )
        if promoted <= 0:
            raise ServiceException(f'目标任务无 canary 可发布: task_id={task_id}')

    @classmethod
    async def _mark_milvus_release_tag(cls, task_id: int, release_tag: str) -> None:
        """按页把本任务向量的 release_tag partial_update 为目标值。"""
        # 与 Embedding 刷库共用批量大小，避免单次 partial_update 过大
        page_size: int = EmbeddingConfig.embedding_embed_batch_size
        # 先统计本任务 VECTOR_STORED 条数，再算总页数（无数据直接返回）
        total: int = await cls._count_task_vectors(task_id)
        total_pages: int = math.ceil(total / page_size) if total > 0 and page_size > 0 else 0
        if total_pages == 0:
            return
        logger.info(
            '[Embedding-publish] Milvus partial_update {}: task_id={}, total={}, page_size={}, pages={}',
            release_tag,
            task_id,
            total,
            page_size,
            total_pages,
        )
        for page_num in range(total_pages):
            # 只拉 embedding_id，不读向量本体
            embedding_ids: list[str] = await cls._fetch_embedding_ids(
                task_id, offset=page_num * page_size, limit=page_size
            )
            if not embedding_ids:
                return
            # Milvus partial_update：VO 只赋 id + release_tag，其余 unset 不提交
            await cls._milvus.partial_update_batch(
                cls._collection,
                [
                    DocumentVectorVo(id=eid, release_tag=release_tag)
                    for eid in embedding_ids
                ],
            )

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _count_task_vectors(cls, task_id: int) -> int:
        return await KnowledgeDocumentSegmentDao.count_vector_stored_by_task(task_id)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _fetch_embedding_ids(
        cls, task_id: int, *, offset: int, limit: int
    ) -> list[str]:
        return await KnowledgeDocumentSegmentDao.list_embedding_ids_by_task(
            task_id,
            offset=offset,
            limit=limit,
        )

    @classmethod
    async def cleanup_pending_delete(cls) -> int:
        """按批清理 pending_delete：删 Milvus → 归档并物理删 MySQL；返回本批条数。"""
        # 1. 按批拉取 pending_delete 分片（无数据直接返回）
        limit: int = EmbeddingConfig.embedding_publish_cleanup_batch_size
        segments: list[KnowledgeDocumentSegment] = await cls._list_pending_delete(limit)
        if not segments:
            return 0

        # 2. 先物理删 Milvus 向量（仅有 embedding_id 的条目）
        embedding_ids: list[str] = [
            s.embedding_id for s in segments if s.embedding_id
        ]
        if embedding_ids:
            await cls._milvus.delete_by_ids(cls._collection, embedding_ids)

        # 3. 再归档并物理删 MySQL（失败可下批重试；向量已在归档表）
        await cls._archive_and_delete_segments([s.id for s in segments])
        logger.info(
            '[Embedding-publish] 清理 pending_delete: count={}, with_vector={}',
            len(segments),
            len(embedding_ids),
        )
        return len(segments)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _list_pending_delete(cls, limit: int) -> list[KnowledgeDocumentSegment]:
        return await KnowledgeDocumentSegmentDao.list_pending_delete_for_cleanup(limit)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _archive_and_delete_segments(cls, segment_ids: list[int]) -> None:
        await KnowledgeDocumentSegmentDao.archive_and_delete_by_ids(
            segment_ids,
            archive_by='admin',
            archive_reason=SegmentArchiveReason.PENDING_DELETE_CLEANUP.value,
        )