"""knowledge-content 原文文件 facade。

提供者：knowledge-content `/internal/documents/{docId}/source-files`
消费者：knowledge-admin 测评集出题。只返回 MinIO 对象键，正文由 admin 自己下载。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class SourceMarkdownFileVo(BaseModel):
    """一篇解析后的 Markdown 在 MinIO 中的位置。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    file_id: int = Field(..., description='knowledge_document_file.id')
    doc_id: int = Field(..., description='文档ID')
    doc_name: str = Field(default='', description='文件名')
    source_url: str | None = Field(default=None, description='来源网页，上传文件为空')
    doc_key: str = Field(..., description='解析后 Markdown 的 MinIO 对象键')


class SourceMarkdownFileListVo(BaseModel):
    """一篇文档下全部可出题的原文文件。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    files: list[SourceMarkdownFileVo] = Field(default_factory=list)
