from __future__ import annotations

from knowledge_common.config.env import EmbeddingConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.service.rag_config_service import RagConfigService
from knowledge_common.utils.snowflake_util import SnowflakeUtil
from knowledge_content.enums.split_type_enum import SplitType
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_file_dao import KnowledgeDocumentFileDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_file_do import KnowledgeDocumentFile
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.splitter import (
    DocumentSplitParamVo,
    DocumentSplitterFactory,
    TextSegmentMetadataVo,
    TextSegmentVo,
)
from knowledge_content.vo.embedding_vo import (
    EmbeddingPreviewRequest,
    EmbeddingPreviewRespVo,
    EmbeddingPreviewSegmentVo,
    EmbeddingSplitParamModel,
)


class EmbeddingPreviewService:
    """切分预览（不落库、不 embed）"""

    @staticmethod
    async def _ensure_chunk_size_within_rerank_limit(chunk_size: int) -> int:
        """块大小不得超过精排单文档字符上限（sys_config: rag.rerank.max_doc_chars）。"""
        max_chars = await RagConfigService.get_rerank_max_doc_chars()
        if chunk_size > max_chars:
            raise ServiceException(
                message=f'块大小不能超过精排单文档上限 {max_chars} 字符（参数 rag.rerank.max_doc_chars）'
            )
        return max_chars

    @staticmethod
    async def _to_split_param(model: EmbeddingSplitParamModel) -> DocumentSplitParamVo:
        await EmbeddingPreviewService._ensure_chunk_size_within_rerank_limit(model.chunk_size)
        try:
            return DocumentSplitParamVo(
                split_type=SplitType(model.split_type),
                chunk_size=model.chunk_size,
                overlap=model.overlap or 0,
                title_level=model.title_level,
                separator=model.separator,
                regex=model.regex,
            )
        except ServiceException:
            raise
        except ValueError as exc:
            raise ServiceException(message=str(exc)) from exc

    @classmethod
    async def _resolve_file(cls, doc_id: int, file_id: int | None) -> KnowledgeDocumentFile:
        """解析预览用的文档文件行。

        file_id 允许为空：预览只取一份 Markdown 样本，不决定正式任务切分范围。
        - 已传 file_id：校验归属后使用该文件
        - 未传：取 id ASC 第一条（上传通常仅一行；爬取则为默认样本页）
        """
        document: KnowledgeDocument | None = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if not document:
            raise ServiceException('文档不存在')

        file_row: KnowledgeDocumentFile | None
        # 显式指定：校验文件属于该文档
        if file_id is not None:
            file_row = await KnowledgeDocumentFileDao.get_by_id(file_id)
            if not file_row or file_row.doc_id != doc_id:
                raise ServiceException('文件不属于该文档或不存在')
            return file_row

        # 未指定：统一取第一条作为预览样本
        file_row = await KnowledgeDocumentFileDao.get_first_by_doc_id(doc_id)
        if not file_row:
            raise ServiceException('文档文件不存在')
        return file_row

    @classmethod
    async def preview(cls, request: EmbeddingPreviewRequest) -> EmbeddingPreviewRespVo:
        """按用户配置试切一段样本，结果仅返回前端，不写 segment / 不调 Embedding。

        流程：
        1. 解析预览文件（可指定 file_id，否则取文档下第一条）
        2. MinIO Range 只拉前缀（上限 embedding_preview_max_chars），避免大文件 OOM；
           truncated=True 表示原文更长，样本已截断
        3. 用请求里的切分参数对样本做一次 split，补齐 chunk_id 后组装响应
        """
        # 1. 定位预览用的 Markdown 文件
        file_row: KnowledgeDocumentFile = await cls._resolve_file(request.doc_id, request.file_id)
        if not file_row.doc_key:
            raise ServiceException('文档对象键为空')

        # 2. Range 拉取前缀样本（非整 文件），控制内存
        max_chars: int = EmbeddingConfig.embedding_preview_max_chars
        sample, truncated = await KnowledgeMinioService.download_content_prefix(
            file_row.doc_key, max_chars
        )

        # 3. 按请求参数切分样本 → 预览分片列表
        split_param: DocumentSplitParamVo = await cls._to_split_param(request)
        segments: list[TextSegmentVo] = DocumentSplitterFactory.get(split_param).split(sample)

        preview_segments: list[EmbeddingPreviewSegmentVo] = []
        for idx, seg in enumerate(segments):
            # 预览不落库，chunk_id 临时生成，仅方便前端展示/对照
            chunk_id: str = seg.chunk_id or SnowflakeUtil.next_id()
            meta: TextSegmentMetadataVo = (seg.metadata or TextSegmentMetadataVo()).model_copy()
            if not meta.chunk_id:
                meta = meta.model_copy(update={'chunk_id': chunk_id})
            preview_segments.append(
                EmbeddingPreviewSegmentVo(
                    order=idx,
                    text=seg.text,
                    length=len(seg.text),
                    skip_embedding=seg.skip_embedding,
                    parent_chunk_id=seg.parent_chunk_id,
                    metadata=meta,
                )
            )

        return EmbeddingPreviewRespVo(
            sample_truncated=truncated,
            sample_length=len(sample),
            sample_text=sample,
            segments=preview_segments,
        )
