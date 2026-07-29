from __future__ import annotations

from typing import Any

from pydantic import Field

from knowledge_common.milvus.vo.base import BaseMilvusVo


class DocumentVectorVo(BaseMilvusVo):
    """``knowledge_document_vector`` collection 行（与 sql/milvus/manage_document_vector.py 对齐）。

    主键为 ``id``（= MySQL ``knowledge_document_segment.embedding_id``）；
    ``chunk_id`` / ``parent_chunk_id`` 对齐 MySQL 分段表，检索侧可直接读父片关系。

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
    parent_chunk_id: str | None = Field(
        default=None,
        max_length=64,
        description='父分片 ID（对齐 segment.parent_chunk_id；无父为空串）',
    )
    text: str | None = Field(default=None, max_length=65535, description='分片正文冗余')
    dept_id: int | None = Field(default=None, description='文档所属部门 ID（data_scope 过滤）')
    user_id: int | None = Field(default=None, description='文档上传用户 ID（data_scope 过滤）')
    # BM25 稀疏向量由 Milvus Function 自动生成；写入勿填；检索默认不输出
    sparse: Any | None = Field(default=None, description='BM25 稀疏向量（Milvus 自动生成）')

    @classmethod
    def output_fields(cls, *, exclude: set[str] | None = None) -> list[str]:
        skip = exclude if exclude is not None else {'vector', 'sparse'}
        return [name for name in cls.model_fields if name not in skip]
