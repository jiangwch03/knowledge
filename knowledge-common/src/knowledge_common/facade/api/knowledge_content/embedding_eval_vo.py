"""knowledge-content embedding 评测 facade 跨服务 VO。

提供者：knowledge-content
消费者：knowledge-admin（禁止在子项目重复定义）
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.vo.base_vo import BaseVo


class CompletedCanaryTaskQuery(BaseVo, BasePageQueryModel):
    """查询已完成且仍为 canary 的向量化任务。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_id: int | None = Field(default=None, description='可选按文档过滤')


class PromoteTaskRequest(BaseVo):
    """将 canary 任务发布为 prod。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    embedding_task_id: int = Field(..., description='要发布的 embedding 任务ID')


class CanaryEmbeddingTaskItemVo(BaseModel):
    """已完成且仍为 canary 的向量化任务列表项。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    task_id: int
    doc_id: int
    source_type: str | None = None
    split_type: str | None = None
    status: str | None = None
    chunk_count: int | None = None
    embedded_count: int | None = None
    embedding_model_code: str | None = None
    dimensions: int | None = None
    create_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None
    doc_title: str | None = None


class EmbeddingTaskForEvalVo(BaseModel):
    """评测绑定用的 embedding 任务详情。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    task_id: int
    doc_id: int
    status: str | None = None
    release_tag: str | None = None
    embedding_model_code: str | None = None
    dimensions: int | None = None
    chunk_count: int | None = None
    embedded_count: int | None = None


class ContentLabelQuery(BaseModel):
    """测评任务列表补名称：按文档 ID、向量化任务 ID 批量取展示名。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_ids: str = Field(default='', description='逗号分隔的文档 ID')
    task_ids: str = Field(default='', description='逗号分隔的向量化任务 ID')


class DocumentTitleItemVo(BaseModel):
    """文档 ID 对应的标题。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_id: int
    doc_title: str = ''


class EmbeddingTaskLabelVo(BaseModel):
    """向量化任务没有独立名称，用切分策略名区分。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    task_id: int
    split_type: str | None = None
    split_type_label: str | None = None


class ContentLabelListVo(BaseModel):
    """文档标题和向量化任务切分策略名。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    documents: list[DocumentTitleItemVo] = Field(default_factory=list)
    embedding_tasks: list[EmbeddingTaskLabelVo] = Field(default_factory=list)
