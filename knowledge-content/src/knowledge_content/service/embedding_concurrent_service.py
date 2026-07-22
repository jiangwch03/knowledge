"""单任务内 Embedding / 刷 Milvus 的队列工人池并发。

与全局「多任务信号量」正交：本模块只解决一个大任务内部批并行——
id 先入队，固定 N 个工人，谁空谁领下一批。
"""
from __future__ import annotations

import asyncio
import math
from collections.abc import Awaitable, Callable

from langchain_core.embeddings import Embeddings

from knowledge_common.common.transactional import PropagationBehavior, transactional
from knowledge_common.config.env import EmbeddingConfig, MilvusConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.milvus import DocumentVectorVo, KnowledgeMilvusClient
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.snowflake_util import SnowflakeUtil
from knowledge_content.enums.segment_status_enum import ReleaseTag, SegmentStatus
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.dao.document_segment_dao import KnowledgeDocumentSegmentDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_content.utils.embedding_vector_codec import pack_embedding_vector, unpack_embedding_vector


class EmbeddingConcurrentService:
    """单任务批并发：阶段一 Embedding 落库、阶段二刷 Milvus。"""

    _milvus = KnowledgeMilvusClient()
    _collection = MilvusConfig.document_vector_collection

    @classmethod
    def _page_size(cls) -> int:
        return max(1, EmbeddingConfig.embedding_embed_batch_size)

    @classmethod
    def _concurrency(cls) -> int:
        return max(1, EmbeddingConfig.embedding_embed_concurrency)

    @classmethod
    def _total_pages(cls, total: int, page_size: int) -> int:
        if total <= 0 or page_size <= 0:
            return 0
        return math.ceil(total / page_size)

    @classmethod
    def _chunk_ids(cls, ids: list[int], page_size: int) -> list[list[int]]:
        return [ids[i : i + page_size] for i in range(0, len(ids), page_size)]

    @classmethod
    async def _run_queue_workers(
        cls,
        *,
        batch_ids: list[list[int]],
        concurrency: int,
        worker_fn: Callable[[list[int], int], Awaitable[None]],
    ) -> None:
        """固定 concurrency 个工人；谁空闲谁立刻从队列领下一批。"""
        if not batch_ids:
            return
        queue: asyncio.Queue[list[int] | None] = asyncio.Queue()
        for chunk in batch_ids:
            queue.put_nowait(chunk)
        for _ in range(concurrency):
            queue.put_nowait(None)

        page_counter = 0
        page_counter_lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal page_counter
            while True:
                ids = await queue.get()
                if ids is None:
                    return
                async with page_counter_lock:
                    page_counter += 1
                    page_num = page_counter
                await worker_fn(ids, page_num)

        await asyncio.gather(*(worker() for _ in range(concurrency)))

    # ── 阶段一：STORED → EMBEDDED ─────────────────────────────────

    @classmethod
    async def embed_pending_segments(cls, task_id: int, embeddings: Embeddings) -> None:
        """待处理 id 入队，工人池持续 Embedding 并落库为 EMBEDDED。"""
        page_size: int = cls._page_size()
        concurrency: int = cls._concurrency()
        pending_ids: list[int] = await cls._list_pending_embed_ids(task_id)
        total: int = len(pending_ids)
        total_pages: int = cls._total_pages(total, page_size)
        if total_pages == 0:
            return

        processed: int = await cls._count_embed_progress(task_id)
        await cls._bump_progress(task_id, processed)
        logger.info(
            '[Embedding] 向量化落库队列: task_id={}, total={}, already={}, page_size={}, '
            'pages={}, workers={}',
            task_id,
            total,
            processed,
            page_size,
            total_pages,
            concurrency,
        )

        progress_lock = asyncio.Lock()

        async def run_batch(ids: list[int], page_num: int) -> None:
            nonlocal processed
            batch: list[KnowledgeDocumentSegment] = await cls._load_segments_by_ids(ids)
            batch = [s for s in batch if s.status == SegmentStatus.STORED.value]
            if not batch:
                return
            logger.info(
                '[Embedding] 向量化落库页: task_id={}, page={}/{}, size={}',
                task_id,
                page_num,
                total_pages,
                len(batch),
            )
            texts: list[str] = [s.text or '' for s in batch]
            vectors: list[list[float]] = await asyncio.to_thread(embeddings.embed_documents, texts)
            if len(vectors) != len(batch):
                raise ServiceException('Embedding 返回向量数量与输入不一致')
            packed: list[tuple[int, bytes]] = [
                (seg.id, pack_embedding_vector(vector))
                for seg, vector in zip(batch, vectors, strict=True)
            ]
            await cls._persist_batch_embedded(packed)
            async with progress_lock:
                processed += len(batch)
                await cls._bump_progress(task_id, processed)

        await cls._run_queue_workers(
            batch_ids=cls._chunk_ids(pending_ids, page_size),
            concurrency=concurrency,
            worker_fn=run_batch,
        )
        logger.info('[Embedding] 向量化落库结束: task_id={}, processed={}', task_id, processed)

    # ── 阶段二：EMBEDDED → VECTOR_STORED ───────────────────────────

    @classmethod
    async def flush_pending_to_milvus(
        cls,
        *,
        task: KnowledgeDocumentEmbeddingTask,
        document: KnowledgeDocument,
    ) -> int:
        """待刷 id 入队，工人池持续刷入 Milvus；返回 VECTOR_STORED 总数。"""
        done_count: int = await cls._count_vector_stored(task.task_id)
        progress_floor: int = await cls._count_embed_progress(task.task_id)
        page_size: int = cls._page_size()
        concurrency: int = cls._concurrency()
        pending_ids: list[int] = await cls._list_pending_milvus_ids(task.task_id)
        pending: int = len(pending_ids)
        total_pages: int = cls._total_pages(pending, page_size)
        if total_pages == 0:
            return done_count

        logger.info(
            '[Embedding] 刷入 Milvus 队列: task_id={}, pending={}, already={}, page_size={}, '
            'pages={}, workers={}',
            task.task_id,
            pending,
            done_count,
            page_size,
            total_pages,
            concurrency,
        )

        progress_lock = asyncio.Lock()

        async def run_batch(ids: list[int], page_num: int) -> None:
            nonlocal done_count
            batch: list[KnowledgeDocumentSegment] = await cls._load_segments_by_ids(
                ids, with_embedding_vector=True
            )
            batch = [s for s in batch if s.status == SegmentStatus.EMBEDDED.value]
            if not batch:
                return
            logger.info(
                '[Embedding] 刷入 Milvus 页: task_id={}, page={}/{}, already={}, size={}',
                task.task_id,
                page_num,
                total_pages,
                done_count,
                len(batch),
            )
            await cls._persist_and_upsert_batch(batch, document)
            async with progress_lock:
                done_count += len(batch)
                await cls._bump_progress(task.task_id, max(progress_floor, done_count))

        await cls._run_queue_workers(
            batch_ids=cls._chunk_ids(pending_ids, page_size),
            concurrency=concurrency,
            worker_fn=run_batch,
        )
        logger.info('[Embedding] 刷入 Milvus 结束: task_id={}, done={}', task.task_id, done_count)
        return done_count

    # ── DAO 短事务 ────────────────────────────────────────────────

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _list_pending_embed_ids(cls, task_id: int) -> list[int]:
        return await KnowledgeDocumentSegmentDao.list_pending_embed_ids_by_task(task_id)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _list_pending_milvus_ids(cls, task_id: int) -> list[int]:
        return await KnowledgeDocumentSegmentDao.list_pending_milvus_ids_by_task(task_id)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _load_segments_by_ids(
        cls,
        ids: list[int],
        *,
        with_embedding_vector: bool = False,
    ) -> list[KnowledgeDocumentSegment]:
        return await KnowledgeDocumentSegmentDao.list_by_ids(
            ids, with_embedding_vector=with_embedding_vector
        )

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _count_embed_progress(cls, task_id: int) -> int:
        return await KnowledgeDocumentSegmentDao.count_embed_progress_by_task(task_id)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _count_vector_stored(cls, task_id: int) -> int:
        return await KnowledgeDocumentSegmentDao.count_vector_stored_by_task(task_id)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _persist_batch_embedded(cls, items: list[tuple[int, bytes]]) -> None:
        await KnowledgeDocumentSegmentDao.batch_update_embedded(items)

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _bump_progress(cls, task_id: int, embedded_count: int) -> None:
        await KnowledgeDocumentEmbeddingTaskDao.update_task(
            task_id,
            embedded_count=embedded_count,
            update_by='admin',
        )

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _persist_and_upsert_batch(
        cls,
        segments: list[KnowledgeDocumentSegment],
        document: KnowledgeDocument,
    ) -> None:
        """先批量更新 DB，再写 Milvus；Milvus 异常则回滚 DB。"""
        db_items: list[tuple[int, str]] = []
        rows: list[DocumentVectorVo] = []
        for seg in segments:
            vector = unpack_embedding_vector(seg.embedding_vector)
            if not vector:
                raise ServiceException(f'分段缺少 embedding_vector: chunk_id={seg.chunk_id}')
            embedding_id: str = seg.embedding_id or SnowflakeUtil.next_id()
            db_items.append((seg.id, embedding_id))
            rows.append(
                DocumentVectorVo(
                    id=embedding_id,
                    vector=vector,
                    doc_id=seg.doc_id,
                    file_id=seg.file_id,
                    task_id=seg.task_id,
                    release_tag=ReleaseTag.CANARY.value,
                    doc_title=document.doc_title or '',
                    doc_version=document.doc_version or '',
                    chunk_id=seg.chunk_id,
                    text=(seg.text or '')[:65535],
                )
            )
        await KnowledgeDocumentSegmentDao.batch_update_vector_stored(db_items)
        await cls._milvus.upsert_batch(cls._collection, rows)
