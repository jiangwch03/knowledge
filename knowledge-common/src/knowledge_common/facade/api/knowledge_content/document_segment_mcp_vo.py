"""knowledge-content 文档分段 MCP 跨服务 VO。

提供者：knowledge-content MCP
消费者：knowledge-admin 等（禁止在子项目重复定义）
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel


class SegmentListQuery(BasePageQueryModel):
    """分段目录分页查询（MCP list）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_id: int = Field(..., description='文档ID')
    release_tag: str | None = Field(default=None, description='可选 canary/prod')
    task_id: int | None = Field(default=None, description='可选 embedding 任务ID')
    page_size: int = Field(default=50, description='每页记录数')


class SegmentGetRequest(BaseModel):
    """按 chunk_id 取正文（MCP get）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_id: int = Field(..., description='文档ID')
    chunk_ids: list[str] = Field(default_factory=list, description='业务 chunk_id 列表')
    release_tag: str | None = Field(default=None, description='可选 canary/prod')
    task_id: int | None = Field(default=None, description='可选 embedding 任务ID')


class SegmentSearchQuery(BaseModel):
    """文档内关键词检索（MCP search）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_id: int = Field(..., description='文档ID')
    query: str = Field(..., description='关键词')
    release_tag: str | None = Field(default=None, description='可选 canary/prod')
    task_id: int | None = Field(default=None, description='可选 embedding 任务ID')
    limit: int = Field(default=10, ge=1, le=50, description='返回条数上限')


class SegmentDirectoryItemVo(BaseModel):
    """分段目录项（无全文）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    chunk_id: str
    chunk_order: int = 0
    task_id: int = 0
    doc_id: int = 0
    file_id: int = 0
    release_tag: str = ''
    preview: str = ''
    text_length: int = 0
    skip_embedding: int = 0
    parent_chunk_id: str | None = None


class SegmentFullItemVo(SegmentDirectoryItemVo):
    """含正文的分段。"""

    text: str = ''


class SegmentListResult(BaseModel):
    """list_document_segments 返回。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    page_num: int = 1
    page_size: int = 50
    total: int = 0
    has_next: bool = False
    rows: list[SegmentDirectoryItemVo] = Field(default_factory=list)
    error: str | None = None


class SegmentGetResult(BaseModel):
    """get_document_segments 返回。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[SegmentFullItemVo] = Field(default_factory=list)
    hint: str = ''
    note: str | None = None
    error: str | None = None


class SegmentSearchResult(BaseModel):
    """search_document_segments 返回。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    items: list[SegmentFullItemVo] = Field(default_factory=list)
    error: str | None = None
