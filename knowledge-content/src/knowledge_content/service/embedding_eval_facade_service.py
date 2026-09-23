"""Embedding 评测发布 facade 编排（admin 调用）。"""
from __future__ import annotations

from knowledge_common.common.vo import PageModel
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.service.embedding_publish_service import EmbeddingPublishService
from knowledge_common.facade.api.knowledge_content.embedding_eval_vo import CanaryEmbeddingTaskItemVo, EmbeddingTaskForEvalVo


class EmbeddingEvalFacadeService:
    """admin 评测编排用：canary 任务查询 + promote。"""

    @classmethod
    async def list_completed_canary_tasks(
        cls,
        *,
        doc_id: int | None = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> PageModel[CanaryEmbeddingTaskItemVo]:
        return await KnowledgeDocumentEmbeddingTaskDao.list_completed_canary_for_eval(
            doc_id=doc_id,
            page_num=page_num,
            page_size=page_size,
        )

    @classmethod
    async def get_task_for_eval(cls, task_id: int) -> EmbeddingTaskForEvalVo:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(
            task_id
        )
        if not task:
            raise ServiceException(f'任务不存在: task_id={task_id}')
        release_map = await KnowledgeDocumentEmbeddingTaskDao.aggregate_release_tags([task_id])
        return EmbeddingTaskForEvalVo(
            task_id=int(task.task_id),
            doc_id=int(task.doc_id),
            status=task.status,
            release_tag=release_map.get(task_id),
            embedding_model_code=task.embedding_model_code,
            dimensions=task.dimensions,
            chunk_count=task.chunk_count,
            embedded_count=task.embedded_count,
        )

    @classmethod
    async def promote(cls, task_id: int) -> None:
        """带任务锁的 promote；仅供评测编排调用。"""
        task: KnowledgeDocumentEmbeddingTask | None = await cls._load_task(task_id)
        if task.status != EmbeddingTaskStatus.COMPLETED.value:
            raise ServiceException(f'仅 COMPLETED 任务可发布: task_id={task_id}, status={task.status}')
        lock_key: str = LockKey.embedding_task_key(task_id)
        async with DistributedLock(lock_key, expire=120, timeout=5) as acquired:
            if not acquired:
                raise ServiceException(f'任务忙碌，无法发布: task_id={task_id}')
            await EmbeddingPublishService.promote_task(task_id)

    @classmethod
    async def _load_task(cls, task_id: int) -> KnowledgeDocumentEmbeddingTask:
        task: KnowledgeDocumentEmbeddingTask | None = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(
            task_id
        )
        if not task:
            raise ServiceException(f'任务不存在: task_id={task_id}')
        return task
