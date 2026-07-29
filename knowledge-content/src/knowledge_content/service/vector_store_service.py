from __future__ import annotations

from knowledge_common.common.transactional import PropagationBehavior, transactional
from knowledge_common.config.env import MilvusConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.milvus import KnowledgeMilvusClient
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.service.embedding_concurrent_service import EmbeddingConcurrentService
from knowledge_content.service.embedding_model_service import EmbeddingModelService


class VectorStoreService:
    """向量化编排：校验 → 并发 Embedding 落库 → 并发刷 Milvus → 完成任务。

    单任务内批并发见 ``EmbeddingConcurrentService``。
    """

    _milvus = KnowledgeMilvusClient()
    _collection = MilvusConfig.document_vector_collection

    @classmethod
    async def delete_by_task_ids(cls, task_ids: list[int]) -> None:
        if not task_ids:
            return
        ids_str: str = ', '.join(str(tid) for tid in task_ids)
        await cls._milvus.delete_by_filter(cls._collection, f'task_id in [{ids_str}]')

    @classmethod
    async def embed_and_store(cls, task: KnowledgeDocumentEmbeddingTask) -> int:
        """两阶段向量化；阶段一/二均走 ``EmbeddingConcurrentService`` 队列工人池并发。

        阶段一 STORED → EMBEDDED：Embedding API + 写 MySQL。
        阶段二 EMBEDDED → VECTOR_STORED：事务内先更新 DB 再 upsert Milvus（批内串行，批间并发）。

        拉批 / 落库均使用 REQUIRES_NEW 独立短事务，避免 consumer 外层 @with_session
        在 MySQL REPEATABLE READ 下一直读到旧快照。
        """
        document: KnowledgeDocument | None = await KnowledgeDocumentDao.get_document_by_id(task.doc_id)
        if not document:
            raise ServiceException('文档不存在')

        # 校验 Milvus collection 维度与任务快照一致
        dimensions: int = task.dimensions or await EmbeddingModelService.get_dimensions()
        await cls._milvus.validate_collection(cls._collection, dimensions)

        # 阶段一：STORED → EMBEDDED（队列工人池并发调 Embedding + 写 MySQL）
        await EmbeddingConcurrentService.embed_pending_segments(task.task_id)
        # 阶段二：EMBEDDED → VECTOR_STORED（队列工人池并发：批内先更新 DB 再 upsert Milvus）
        embedded_count: int = await EmbeddingConcurrentService.flush_pending_to_milvus(
            task=task,
            document=document,
        )
        # 阶段三：全部成功后标记任务 COMPLETED
        await cls._finalize_embed(task.task_id, embedded_count)
        return embedded_count

    @classmethod
    @transactional(propagation=PropagationBehavior.REQUIRES_NEW, rollback_for=(Exception,))
    async def _finalize_embed(cls, task_id: int, embedded_count: int) -> None:
        """全部刷库成功后推进任务状态。"""
        await KnowledgeDocumentEmbeddingTaskDao.update_task(
            task_id,
            status=EmbeddingTaskStatus.COMPLETED.value,
            embedded_count=embedded_count,
            update_by='admin',
        )
