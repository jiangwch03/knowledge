from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from knowledge_common.common.transactional import transactional
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.service.rag_config_service import RagConfigService
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.snowflake_util import SnowflakeUtil
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.enums.segment_status_enum import ReleaseTag, SegmentArchiveReason, SegmentStatus
from knowledge_content.enums.split_type_enum import SplitType
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_file_dao import KnowledgeDocumentFileDao
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.dao.document_segment_dao import KnowledgeDocumentSegmentDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_file_do import KnowledgeDocumentFile
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.service.vector_store_service import VectorStoreService
from knowledge_content.splitter import (
    DocumentSplitParamVo,
    DocumentSplitterFactory,
    TextSegmentMetadataVo,
    TextSegmentVo,
)
from knowledge_content.splitter.base import BaseDocumentSplitter


class DocumentSplitService:
    """文档切分落库（canary 语义，不触碰 prod）"""

    @staticmethod
    async def _parse_split_param(task: KnowledgeDocumentEmbeddingTask) -> DocumentSplitParamVo:
        raw: Any = task.split_params
        if not raw:
            raise ServiceException('任务切分参数为空')
        data: dict[str, Any] = json.loads(raw) if isinstance(raw, str) else raw
        try:
            chunk_size = int(data['chunkSize'])
            max_chars = await RagConfigService.get_rerank_max_doc_chars()
            if chunk_size > max_chars:
                raise ServiceException(
                    message=f'块大小不能超过精排单文档上限 {max_chars} 字符（参数 rag.rerank.max_doc_chars）'
                )
            return DocumentSplitParamVo(
                split_type=SplitType(data.get('splitType') or task.split_type),
                chunk_size=chunk_size,
                overlap=int(data.get('overlap') or 0),
                title_level=data.get('titleLevel'),
                separator=data.get('separator'),
                regex=data.get('regex'),
            )
        except ServiceException:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise ServiceException(message=f'切分参数无效: {exc}') from exc

    @staticmethod
    def _enrich_metadata(
        seg: TextSegmentVo,
        *,
        doc_id: int,
        file_id: int,
        task_id: int,
        doc_title: str | None,
        doc_version: str | None,
        file_name: str | None,
        source_url: str | None,
        chunk_id: str,
    ) -> TextSegmentMetadataVo:
        base: TextSegmentMetadataVo = seg.metadata or TextSegmentMetadataVo()
        return base.model_copy(
            update={
                'chunk_id': chunk_id,
                'doc_id': doc_id,
                'file_id': file_id,
                'task_id': task_id,
                'release_tag': ReleaseTag.CANARY.value,
                'doc_title': doc_title,
                'doc_version': doc_version,
                'file_name': file_name,
                'source_url': source_url,
                'skip_embedding': seg.skip_embedding,
                'parent_chunk_id': seg.parent_chunk_id,
            },
        )

    @classmethod
    async def split_document(cls, task: KnowledgeDocumentEmbeddingTask) -> int:
        """按 file_id 逐个切分落库：每个文件下载+切分+写库在同一事务内；全部成功后推进状态。"""
        # 1. 校验文档与文件列表
        document: KnowledgeDocument | None = await KnowledgeDocumentDao.get_document_by_id(task.doc_id)
        if not document:
            raise ServiceException('文档不存在')

        files: list[KnowledgeDocumentFile] = await KnowledgeDocumentFileDao.list_by_doc_id(task.doc_id)
        if not files:
            raise ServiceException('文档文件不存在')

        # 2. 断点续跑：单 file 事务已提交的视为完成，失败重试只处理未落库文件
        done_file_ids: set[int] = await KnowledgeDocumentSegmentDao.list_file_ids_by_task(task.task_id)
        pending_files: list[KnowledgeDocumentFile] = [f for f in files if f.id not in done_file_ids]
        if done_file_ids:
            logger.info(
                '[Embedding] 跳过已切分文件: task_id={}, done={}, pending={}',
                task.task_id,
                len(done_file_ids),
                len(pending_files),
            )

        # 3. 构建切分器（参数来自任务快照，重试不改策略）
        split_param: DocumentSplitParamVo = await cls._parse_split_param(task)
        splitter: BaseDocumentSplitter = DocumentSplitterFactory.get(split_param)

        # 4. 逐文件切分；chunk_count 仅统计需入向量库的分片（不含父片）
        for file_row in pending_files:
            await cls._split_and_persist_file(
                task=task,
                document=document,
                file_row=file_row,
                splitter=splitter,
            )
        chunk_count: int = await KnowledgeDocumentSegmentDao.count_by_task(
            task.task_id,
            skip_embedding=0,
        )

        # 5. 全部文件完成后：任务推进 EMBEDDING
        await cls._finalize_split(task.task_id, chunk_count)
        return chunk_count

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _split_and_persist_file(
        cls,
        *,
        task: KnowledgeDocumentEmbeddingTask,
        document: KnowledgeDocument,
        file_row: KnowledgeDocumentFile,
        splitter: BaseDocumentSplitter,
    ) -> int:
        """单 file 事务：下载 → 切分 → 插入。chunk_order 仅在文件内从 0 递增。"""
        if not file_row.doc_key:
            raise ServiceException(f'文件 doc_key 为空: file_id={file_row.id}')

        text: str = await KnowledgeMinioService.download_content(file_row.doc_key)
        segments: list[TextSegmentVo] = splitter.split(text)

        now: datetime = datetime.now()
        rows: list[KnowledgeDocumentSegment] = []
        for idx, seg in enumerate(segments):
            chunk_id: str = seg.chunk_id or SnowflakeUtil.next_id()
            metadata: TextSegmentMetadataVo = cls._enrich_metadata(
                seg,
                doc_id=task.doc_id,
                file_id=file_row.id,
                task_id=task.task_id,
                doc_title=document.doc_title,
                doc_version=document.doc_version,
                file_name=file_row.doc_name,
                source_url=file_row.source_url,
                chunk_id=chunk_id,
            )
            rows.append(
                KnowledgeDocumentSegment(
                    task_id=task.task_id,
                    doc_id=task.doc_id,
                    file_id=file_row.id,
                    chunk_id=chunk_id,
                    chunk_order=idx,
                    text=seg.text,
                    metadata_json=json.dumps(
                        metadata.model_dump(by_alias=True, exclude_none=True),
                        ensure_ascii=False,
                    ),
                    parent_chunk_id=seg.parent_chunk_id,
                    skip_embedding=1 if seg.skip_embedding else 0,
                    status=SegmentStatus.STORED.value,
                    release_tag=ReleaseTag.CANARY.value,
                    create_by=task.create_by or 'admin',
                    create_time=now,
                    update_by=task.create_by or 'admin',
                    update_time=now,
                )
            )

        await KnowledgeDocumentSegmentDao.bulk_insert(rows)
        logger.info(
            '[Embedding] 文件切分落库完成: task_id={}, file_id={}, chunks={}',
            task.task_id,
            file_row.id,
            len(rows),
        )
        return len(rows)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _finalize_split(cls, task_id: int, chunk_count: int) -> None:
        """全部文件切分成功后推进任务状态。"""
        await KnowledgeDocumentEmbeddingTaskDao.update_task(
            task_id,
            status=EmbeddingTaskStatus.EMBEDDING.value,
            chunk_count=chunk_count,
            update_by='admin',
        )

    @classmethod
    async def cleanup_task_residue(cls, task_id: int, update_by: str = 'admin') -> None:
        """清理任务残留：归档并物理删 MySQL；向量已在归档表。"""
        # 1. 归档并物理删 MySQL
        await KnowledgeDocumentSegmentDao.archive_and_delete_by_task(
            task_id,
            archive_by=update_by,
            archive_reason=SegmentArchiveReason.TASK_RESIDUE.value,
        )
        # 2. 物理删 Milvus
        await VectorStoreService.delete_by_task_ids([task_id])
