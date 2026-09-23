"""文档分段 MCP 工具：list / get / search，复用 DocumentSegmentQueryService。"""
from __future__ import annotations

from knowledge_content.server.mcp_server import server
from knowledge_content.service.document_segment_query_service import DocumentSegmentQueryService
from knowledge_common.facade.api.knowledge_content.document_segment_mcp_vo import (
    SegmentGetRequest,
    SegmentGetResult,
    SegmentListQuery,
    SegmentListResult,
    SegmentSearchQuery,
    SegmentSearchResult,
)

# 与 EmbeddingConfig.embedding_segment_get_batch_limit 对齐的默认说明
_GET_BATCH_HINT = '单次 chunk_ids 条数受 content 配置 embedding_segment_get_batch_limit 限制'


@server.tool()
async def list_document_segments(query: SegmentListQuery) -> SegmentListResult:
    """摸目录：返回分段元数据与预览，不含全文。"""
    page = await DocumentSegmentQueryService.list_segments(query)
    return SegmentListResult(
        page_num=page.page_num,
        page_size=page.page_size,
        total=page.total,
        has_next=page.has_next,
        rows=list(page.rows or []),
    )


@server.tool()
async def get_document_segments(request: SegmentGetRequest) -> SegmentGetResult:
    """按需取正文。"""
    items = await DocumentSegmentQueryService.get_segments(request)
    return SegmentGetResult(items=items, hint=_GET_BATCH_HINT)


@server.tool()
async def search_document_segments(query: SegmentSearchQuery) -> SegmentSearchResult:
    """文档内关键词补洞检索。"""
    items = await DocumentSegmentQueryService.search_segments(query)
    return SegmentSearchResult(items=items)
