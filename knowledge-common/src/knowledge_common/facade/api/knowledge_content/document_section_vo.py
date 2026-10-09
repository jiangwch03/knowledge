"""knowledge-content 出题切节 facade。

提供者：knowledge-content `/internal/documents/{docId}/sections`
消费者：knowledge-admin 测评集出题。只给上传文档的 Markdown 用，不落分段表。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class DocumentSectionVo(BaseModel):
    """按标题或字数切出的一节。不是向量分段。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    section_order: int = Field(..., description='顺序，从 0 起')
    title: str = Field(default='', description='标题。按字数切开时为空')
    parent_title: str = Field(default='', description='上级标题。没有上级时为空')
    body: str = Field(default='', description='这一节的正文')


class DocumentSectionListVo(BaseModel):
    """一篇上传文档切出的全部节。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    sections: list[DocumentSectionVo] = Field(default_factory=list)
