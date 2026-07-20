from __future__ import annotations

from pydantic import Field

from knowledge_common.milvus.vo.base import BaseMilvusVo


class DocumentVectorVo(BaseMilvusVo):
    """``knowledge_document_vector`` collection 行（与 sql/milvus/manage_document_vector.py 对齐）。"""

    id: str = Field(..., max_length=64, description='embedding_id，向量主键')
    vector: list[float] = Field(..., description='embedding 稠密向量')
    doc_id: int = Field(..., description='文档 ID')
    file_id: int = Field(..., description='文件 ID')
    task_id: int = Field(..., description='向量化任务 ID')
    release_tag: str = Field(
        ...,
        max_length=32,
        description='发布标签：canary / prod / pending_delete',
    )
    doc_title: str = Field(default='', max_length=512, description='文档标题冗余')
    doc_version: str = Field(default='', max_length=64, description='文档版本冗余')
    chunk_id: str = Field(..., max_length=64, description='分片 ID')
    text: str = Field(default='', max_length=65535, description='分片正文冗余')
