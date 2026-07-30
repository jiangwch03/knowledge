from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.config.env import SemaphoreConfig, StreamTopicConfig
from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.redis import DistributedLock, DistributedSemaphore, LockKey, SemaphoreKey
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.enums.split_type_enum import SplitType
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.dao.document_segment_dao import KnowledgeDocumentSegmentDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.service.document_split_service import DocumentSplitService
from knowledge_content.service.embedding_model_service import EmbeddingModelService
from knowledge_content.service.embedding_preview_service import EmbeddingPreviewService
from knowledge_content.service.vector_store_service import VectorStoreService
from knowledge_content.service.vo.message_stream_topic_vo import EmbeddingPending
from knowledge_content.vo.embedding_vo import (
    EmbeddingCreateTaskRequest,
    EmbeddingCreateTaskRespVo,
    EmbeddingModelInfoVo,
    EmbeddingSegmentListQuery,
    EmbeddingTaskDetailVo,
    EmbeddingTaskListItemVo,
    EmbeddingTaskListQuery,
)

# 全局并发控制：限制多 worker 下同时执行的切分+向量化任务数
# 无可用令牌时 BLPOP 挂起，令牌归还后自动唤醒
_embedding_semaphore: DistributedSemaphore | None = None


async def _get_embedding_semaphore() -> DistributedSemaphore:
    """懒初始化 Embedding 流水线信号量（多 worker 下 create_pool 仅执行一次）。"""
    global _embedding_semaphore
    if _embedding_semaphore is None:
        max_concurrent: int = SemaphoreConfig.semaphore_embedding_pipeline_size
        key: str = SemaphoreKey.embedding_pipeline_key()
        await DistributedSemaphore.create_pool(key=key, size=max_concurrent)
        _embedding_semaphore = DistributedSemaphore(key=key)
    return _embedding_semaphore


class EmbeddingTaskService:
    """Embedding 任务 CRUD 与异步流水线"""

    @classmethod
    async def _split_params_payload(cls, request: EmbeddingCreateTaskRequest) -> dict[str, Any]:
        await EmbeddingPreviewService._to_split_param(request)
        payload: dict[str, Any] = {
            'splitType': request.split_type,
            'chunkSize': request.chunk_size,
            'overlap': request.overlap or 0,
            'titleLevel': request.title_level,
            'separator': request.separator,
            'regex': request.regex,
        }
        if request.split_type == SplitType.SMART.value:
            payload['overlap'] = int(request.chunk_size * 0.1)
        return payload

    @classmethod
    async def _validate_document(cls, doc_id: int) -> KnowledgeDocument:
        document: KnowledgeDocument | None = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if not document:
            raise ServiceException('文档不存在')
        if await KnowledgeDocumentEmbeddingTaskDao.has_in_progress(doc_id):
            raise ServiceException('该文档已有进行中的 Embedding 任务，请先删除后再新建')
        if await KnowledgeDocumentSegmentDao.has_canary_by_doc(doc_id):
            raise ServiceException('该文档已有未发布的 Embedding 结果，请先删除对应任务后再新建')
        return document

    @classmethod
    async def _publish_pending(cls, task_id: int) -> None:
        try:
            await MessageStreamService.produce(
                topic=StreamTopicConfig.embedding_pending,
                value=EmbeddingPending(task_id=task_id),
                key=str(task_id),
            )
        except Exception as exc:
            err: str = format_exception_message(exc)
            logger.exception('发布 embedding.pending 失败: task_id={}, error={}', task_id, err)
            raise ServiceException(f'发布 Embedding 消息失败: {err}') from exc

    @classmethod
    async def create_task(
        cls,
        request: EmbeddingCreateTaskRequest,
        current_user: CurrentUserModel,
    ) -> EmbeddingCreateTaskRespVo:
        saved: KnowledgeDocumentEmbeddingTask = await cls._create_task(request, current_user)
        await cls._publish_pending(saved.task_id)
        return EmbeddingCreateTaskRespVo(task_id=saved.task_id)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _create_task(
        cls,
        request: EmbeddingCreateTaskRequest,
        current_user: CurrentUserModel,
    ) -> KnowledgeDocumentEmbeddingTask:
        """校验文档并落库 Embedding 任务（PENDING）；消息发布由 create_task 在事务提交后执行。"""
        document: KnowledgeDocument = await cls._validate_document(request.doc_id)
        # 一期锁定的 Embedding 模型与维度
        model_info: EmbeddingModelInfoVo = await EmbeddingModelService.get_model_info()
        split_params: dict[str, Any] = await cls._split_params_payload(request)
        now: datetime = datetime.now()

        task: KnowledgeDocumentEmbeddingTask = KnowledgeDocumentEmbeddingTask(
            doc_id=request.doc_id,
            source_type=document.source_type,
            split_type=request.split_type,
            split_params=json.dumps(split_params, ensure_ascii=False),
            status=EmbeddingTaskStatus.PENDING.value,
            embedding_model_code=model_info.model_code,
            dimensions=model_info.dimensions,
            user_id=current_user.user.user_id,
            dept_id=current_user.user.dept_id,
            create_by=current_user.user.user_name,
            update_by=current_user.user.user_name,
            create_time=now,
            update_time=now,
        )
        return await KnowledgeDocumentEmbeddingTaskDao.add_task(task)

    @classmethod
    async def list_tasks(cls, query: EmbeddingTaskListQuery) -> PageModel:
        page: PageModel = await KnowledgeDocumentEmbeddingTaskDao.list_tasks(
            status=query.status,
            source_type=query.source_type,
            doc_id=query.doc_id,
            doc_title=query.doc_title,
            begin_time=query.begin_time,
            end_time=query.end_time,
            page_num=query.page_num,
            page_size=query.page_size,
        )
        task_ids: list[int] = [row['taskId'] for row in page.rows if row.get('taskId')]
        release_map: dict[int, str | None] = await KnowledgeDocumentEmbeddingTaskDao.aggregate_release_tags(task_ids)
        rows: list[EmbeddingTaskListItemVo] = []
        for row in page.rows:
            item: EmbeddingTaskListItemVo = EmbeddingTaskListItemVo.model_validate(row)
            item.release_tag = release_map.get(item.task_id)
            rows.append(item)
        page.rows = rows
        return page

    @classmethod
    async def get_task_detail(cls, task_id: int) -> EmbeddingTaskDetailVo:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            raise ServiceException('任务不存在')
        document: KnowledgeDocument | None = await KnowledgeDocumentDao.get_document_by_id(task.doc_id)
        release_map: dict[int, str | None] = await KnowledgeDocumentEmbeddingTaskDao.aggregate_release_tags([task_id])
        split_params: Any = task.split_params
        if isinstance(split_params, str):
            try:
                split_params = json.loads(split_params)
            except json.JSONDecodeError:
                pass
        return EmbeddingTaskDetailVo(
            task_id=task.task_id,
            doc_id=task.doc_id,
            doc_title=document.doc_title if document else None,
            source_type=task.source_type,
            split_type=task.split_type,
            status=task.status,
            release_tag=release_map.get(task_id),
            chunk_count=task.chunk_count,
            embedded_count=task.embedded_count,
            embedding_model_code=task.embedding_model_code,
            dimensions=task.dimensions,
            error_message=task.error_message,
            create_by=task.create_by,
            create_time=task.create_time,
            update_time=task.update_time,
            split_params=split_params,
        )

    @classmethod
    async def list_task_segments(cls, task_id: int, query: EmbeddingSegmentListQuery) -> PageModel:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            raise ServiceException('任务不存在')
        page: PageModel = await KnowledgeDocumentSegmentDao.list_by_task_page(
            task_id,
            skip_embedding=query.skip_embedding,
            page_num=query.page_num,
            page_size=query.page_size,
        )
        rows: list[Any] = []
        for row in page.rows:
            meta: Any = row.get('metadataJson') if isinstance(row, dict) else None
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    pass
            if isinstance(row, dict):
                item: dict[str, Any] = dict(row)
                item['metadata'] = meta
                item.pop('metadataJson', None)
                rows.append(item)
            else:
                rows.append(row)
        page.rows = rows
        return page

    @classmethod
    async def retry_task(cls, task_id: int, current_user: CurrentUserModel) -> EmbeddingCreateTaskRespVo:
        """失败就地重试：不改切分参数；按失败阶段回到 CHUNKING / EMBEDDING。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            raise ServiceException('任务不存在')
        if task.status not in EmbeddingTaskStatus.failed_values():
            raise ServiceException('仅失败任务可重试')

        lock_key: str = LockKey.embedding_task_key(task_id)
        async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
            if not acquired:
                raise ServiceException('任务正在处理中，请稍后重试')
            await cls._reset_failed_task(task_id, update_by=current_user.user.user_name)

        await cls._publish_pending(task_id)
        return EmbeddingCreateTaskRespVo(task_id=task_id)

    @classmethod
    async def auto_retry_failed(cls, task_id: int) -> None:
        """失败自动重试：重置到 CHUNKING/EMBEDDING 后重投递（调度兜底用）。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task or task.status not in EmbeddingTaskStatus.failed_values():
            return

        lock_key: str = LockKey.embedding_task_key(task_id)
        async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
            if not acquired:
                return
            await cls._reset_failed_task(task_id, update_by='admin')

        await cls._publish_pending(task_id)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _reset_failed_task(cls, task_id: int, update_by: str = 'admin') -> None:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            raise ServiceException('任务不存在')
        if task.status not in EmbeddingTaskStatus.failed_values():
            raise ServiceException('仅失败任务可重试')
        if await KnowledgeDocumentEmbeddingTaskDao.has_in_progress(task.doc_id):
            raise ServiceException('该文档已有进行中的 Embedding 任务')

        # 按失败阶段续跑，不回 PENDING：切分失败 → CHUNKING；向量化失败 → EMBEDDING
        if task.status == EmbeddingTaskStatus.CHUNK_FAILED.value:
            # 保留已切分 file 的 segment，由 split_document 跳过已完成文件
            await KnowledgeDocumentEmbeddingTaskDao.update_task(
                task_id,
                status=EmbeddingTaskStatus.CHUNKING.value,
                error_message='',
                update_by=update_by,
            )
            return

        # EMBED_FAILED：保留切分结果与已 VECTOR_STORED 分段，续跑只处理未完成段
        await KnowledgeDocumentEmbeddingTaskDao.update_task(
            task_id,
            status=EmbeddingTaskStatus.EMBEDDING.value,
            error_message='',
            update_by=update_by,
        )

    @classmethod
    async def delete_task(cls, task_id: int, current_user: CurrentUserModel) -> None:
        """删除进行中 / 失败 / 未发布(canary) 任务；已发布(prod)、已归档不可删。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            raise ServiceException('任务不存在')

        lock_key: str = LockKey.embedding_task_key(task_id)
        async with DistributedLock(lock_key, expire=60, timeout=0) as acquired:
            if not acquired:
                raise ServiceException('任务正在处理中，请稍后重试')
            await cls._delete_task(task_id, current_user.user.user_name)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _delete_task(cls, task_id: int, update_by: str) -> None:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            raise ServiceException('任务不存在')
        if await KnowledgeDocumentSegmentDao.has_prod_by_task(task_id):
            raise ServiceException('已发布（prod）任务不可删除')
        # 已完成且无分片：已被发布替换并归档清理，禁止再删（任务记录保留作审计）
        if task.status == EmbeddingTaskStatus.COMPLETED.value and not await KnowledgeDocumentSegmentDao.has_segments_by_task(
            task_id
        ):
            raise ServiceException('已归档任务不可删除')
        # 1. 清理任务残留
        await DocumentSplitService.cleanup_task_residue(task_id, update_by=update_by)
        # 2. 软删除任务表
        await KnowledgeDocumentEmbeddingTaskDao.soft_delete(task_id, update_by=update_by)

    @classmethod
    async def process_pending(cls, task_id: int) -> None:
        """消费端入口：按状态推进 PENDING → CHUNKING → EMBEDDING → COMPLETED，支持断点续跑。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            logger.info('[Embedding] 任务不存在，跳过: task_id={}', task_id)
            return
        # 终态直接跳过；并发互斥由消费端 DistributedLock 保证
        if task.status in EmbeddingTaskStatus.terminal_values():
            logger.info('[Embedding] 任务已终态，跳过: task_id={}, status={}', task_id, task.status)
            return

        # 全局并发上限：先 task 锁（consumer）再等令牌，避免占槽后发现任务已被处理
        semaphore: DistributedSemaphore = await _get_embedding_semaphore()
        async with semaphore:
            await cls._process_pending_pipeline(task_id, task)

    @classmethod
    async def _process_pending_pipeline(
        cls,
        task_id: int,
        task: KnowledgeDocumentEmbeddingTask,
    ) -> None:
        """在信号量保护下执行切分 + 向量化流水线。"""
        # PENDING → CHUNKING：进入切分阶段
        if task.status == EmbeddingTaskStatus.PENDING.value:
            await KnowledgeDocumentEmbeddingTaskDao.update_task(
                task_id,
                status=EmbeddingTaskStatus.CHUNKING.value,
                update_by='admin',
            )
            task = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
            if not task:
                return

        # 阶段一：文档切分；事务内落库并推进为 EMBEDDING
        if task.status == EmbeddingTaskStatus.CHUNKING.value:
            try:
                await DocumentSplitService.split_document(task)
            except Exception as exc:
                err: str = format_exception_message(exc)
                logger.exception('[Embedding] 切分失败: task_id={}, error={}', task_id, err)
                await KnowledgeDocumentEmbeddingTaskDao.update_task(
                    task_id,
                    status=EmbeddingTaskStatus.CHUNK_FAILED.value,
                    error_message=err,
                    update_by='admin',
                )
                return

        # 阶段二：向量化并写入向量库；内部会将任务置为 COMPLETED
        # DAO 短事务各自提交；直接重读即可看到已提交的 EMBEDDING。
        task = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task:
            return
        if task.status != EmbeddingTaskStatus.EMBEDDING.value:
            logger.info(
                '[Embedding] 跳过向量化: task_id={}, status={}',
                task_id,
                task.status,
            )
            return
        try:
            await VectorStoreService.embed_and_store(task)
            logger.info('[Embedding] 任务完成: task_id={}', task_id)
        except Exception as exc:
            err = format_exception_message(exc)
            logger.exception('[Embedding] 向量化失败: task_id={}, error={}', task_id, err)
            await KnowledgeDocumentEmbeddingTaskDao.update_task(
                task_id,
                status=EmbeddingTaskStatus.EMBED_FAILED.value,
                error_message=err,
                update_by='admin',
            )
            # 已提交的 VECTOR_STORED 分段保留；重试从剩余 STORED 段续跑

    @classmethod
    async def republish_pending(cls, task_id: int) -> None:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task or task.status != EmbeddingTaskStatus.PENDING.value:
            return
        await cls._publish_pending(task_id)

    @classmethod
    async def republish_stuck(cls, task_id: int) -> None:
        """僵尸 CHUNKING/EMBEDDING：刷新 update_time 后重投递，消费端按状态断点续跑。"""
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if not task or task.status not in (
            EmbeddingTaskStatus.CHUNKING.value,
            EmbeddingTaskStatus.EMBEDDING.value,
        ):
            return
        # 刷新 update_time，避免调度每轮重复投递
        await KnowledgeDocumentEmbeddingTaskDao.update_task(task_id, update_by='admin')
        await cls._publish_pending(task_id)
