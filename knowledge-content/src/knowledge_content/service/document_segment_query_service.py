"""文档分段查询，供内部分页接口使用。"""
from __future__ import annotations

from knowledge_common.common.vo import PageModel
from knowledge_common.config.env import EmbeddingConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_content.mapper.dao.document_segment_dao import KnowledgeDocumentSegmentDao
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_common.facade.api.knowledge_content.segment_facade_vo import (
    SegmentDirectoryItemVo,
    SegmentFullItemVo,
    SegmentGetRequest,
    SegmentListQuery,
    SegmentSearchQuery,
)


class DocumentSegmentQueryService:
    """文档分段查询：目录分页与全文分页。"""

    _FULL_PAGE_SIZE_MAX = 500

    @classmethod
    async def list_segments(cls, query: SegmentListQuery) -> PageModel[SegmentDirectoryItemVo]:
        """摸目录：分页返回分段元数据与预览，不含全文。"""
        return await KnowledgeDocumentSegmentDao.list_by_doc_page(
            query.doc_id,
            release_tag=query.release_tag,
            task_id=query.task_id,
            page_num=query.page_num,
            page_size=query.page_size,
        )

    @classmethod
    async def list_full_segments(cls, query: SegmentListQuery) -> PageModel[SegmentFullItemVo]:
        """按 doc_id 分页返回正文。单页最多 500 条。"""
        page_size = min(max(query.page_size, 1), cls._FULL_PAGE_SIZE_MAX)
        return await KnowledgeDocumentSegmentDao.list_full_by_doc_page(
            query.doc_id,
            release_tag=query.release_tag,
            task_id=query.task_id,
            page_num=query.page_num,
            page_size=page_size,
        )

    @classmethod
    async def get_segments(cls, request: SegmentGetRequest) -> list[SegmentFullItemVo]:
        """按 chunk_id 批量取正文；去重后校验单次条数上限。"""
        limit_k: int = EmbeddingConfig.embedding_segment_get_batch_limit
        chunk_ids: list[str] = list(dict.fromkeys(request.chunk_ids or []))
        if not chunk_ids:
            return []
        if len(chunk_ids) > limit_k:
            raise ServiceException(f'单次最多获取 {limit_k} 个分段')
        segments: list[KnowledgeDocumentSegment] = await KnowledgeDocumentSegmentDao.list_by_chunk_ids(
            request.doc_id,
            chunk_ids,
            release_tag=request.release_tag,
            task_id=request.task_id,
        )
        return [cls._to_full_item(s) for s in segments]

    @classmethod
    async def search_segments(cls, query: SegmentSearchQuery) -> list[SegmentFullItemVo]:
        """文档内关键词检索（补洞），返回含正文的匹配分段。"""
        segments: list[KnowledgeDocumentSegment] = await KnowledgeDocumentSegmentDao.search_by_doc(
            query.doc_id,
            query.query,
            release_tag=query.release_tag,
            task_id=query.task_id,
            limit=query.limit,
        )
        return [cls._to_full_item(s) for s in segments]

    @staticmethod
    def _to_full_item(segment: KnowledgeDocumentSegment) -> SegmentFullItemVo:
        """DO → 带正文的分段 VO。"""
        text: str = segment.text or ''
        return SegmentFullItemVo(
            chunk_id=str(segment.chunk_id),
            chunk_order=int(segment.chunk_order or 0),
            task_id=int(segment.task_id),
            doc_id=int(segment.doc_id),
            file_id=int(segment.file_id),
            release_tag=str(segment.release_tag or ''),
            text=text,
            text_length=len(text),
            skip_embedding=int(segment.skip_embedding or 0),
            parent_chunk_id=segment.parent_chunk_id,
        )
