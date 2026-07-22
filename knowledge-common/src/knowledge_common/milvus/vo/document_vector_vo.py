from __future__ import annotations

from pydantic import Field

from knowledge_common.milvus.vo.base import BaseMilvusVo


class DocumentVectorVo(BaseMilvusVo):
    """``knowledge_document_vector`` collection 行（与 sql/milvus/manage_document_vector.py 对齐）。

    主键为 ``id``（= MySQL ``knowledge_document_segment.embedding_id``）；
    ``chunk_id`` 为业务分片关联字段，便于从向量命中回查 MySQL。

    全量写入时填齐字段；部分更新时只赋值要改的字段（其余保持 unset，经 ``to_partial_row``）。
    """

    id: str = Field(..., max_length=64, description='Milvus 主键（= segment.embedding_id）')
    vector: list[float] | None = Field(default=None, description='embedding 稠密向量')
    doc_id: int | None = Field(default=None, description='文档 ID')
    file_id: int | None = Field(default=None, description='文件 ID')
    task_id: int | None = Field(default=None, description='向量化任务 ID')
    release_tag: str | None = Field(
        default=None,
        max_length=32,
        description='发布标签：canary / prod / pending_delete',
    )
    doc_title: str | None = Field(default=None, max_length=512, description='文档标题冗余')
    doc_version: str | None = Field(default=None, max_length=64, description='文档版本冗余')
    chunk_id: str | None = Field(default=None, max_length=64, description='业务分片 ID（对齐 segment.chunk_id）')
    text: str | None = Field(default=None, max_length=65535, description='分片正文冗余')
