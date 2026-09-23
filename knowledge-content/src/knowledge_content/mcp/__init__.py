"""knowledge-content MCP 工具接口。"""

from knowledge_content.mcp.segment_mcp import (
    get_document_segments,
    list_document_segments,
    search_document_segments,
)

__all__ = [
    'list_document_segments',
    'get_document_segments',
    'search_document_segments',
]
