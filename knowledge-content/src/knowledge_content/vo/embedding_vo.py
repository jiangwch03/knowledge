from datetime import datetime
from typing import Any
import json

from pydantic import ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.vo.base_vo import BaseVo
from knowledge_content.splitter.vo import TextSegmentMetadataVo


class EmbeddingSplitParamModel(BaseVo):
    """切分参数（预览 / 提交共用）"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    split_type: str = Field(..., description='切分策略 TITLE/LENGTH/SEPARATOR/REGEX/SMART')
    chunk_size: int = Field(..., description='块大小')
    overlap: int | None = Field(default=0, description='重叠长度')
    title_level: int | None = Field(default=None, description='TITLE 标题层级 1-6')
    separator: str | None = Field(default=None, description='SEPARATOR 字面量分隔符（系统字典 document_split_separator）')
    regex: str | None = Field(default=None, description='REGEX 正则')

    @NotBlank(field_name='split_type', message='切分策略不能为空')
    def get_split_type(self) -> str:
        return self.split_type


class EmbeddingPreviewRequest(EmbeddingSplitParamModel):
    """预览请求"""

    doc_id: int = Field(..., description='文档ID')
    # 可空：缺省取 id ASC 第一条作为预览样本（上传通常仅一行）。仅影响预览，不决定正式任务切分范围
    file_id: int | None = Field(default=None, description='文件行ID（可选，缺省取第一条）')


class EmbeddingCreateTaskRequest(EmbeddingSplitParamModel):
    """创建 Embedding 任务"""

    doc_id: int = Field(..., description='文档ID')


class EmbeddingPreviewSegmentVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    order: int = Field(..., description='序号')
    text: str = Field(..., description='文本')
    length: int = Field(..., description='长度')
    skip_embedding: bool = Field(default=False, description='是否跳过向量化')
    parent_chunk_id: str | None = Field(default=None, description='父分片ID')
    metadata: TextSegmentMetadataVo = Field(
        default_factory=TextSegmentMetadataVo,
        description='元数据',
    )


class EmbeddingPreviewRespVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    sample_truncated: bool = Field(..., description='样本是否截断')
    sample_length: int = Field(..., description='样本长度')
    sample_text: str = Field(default='', description='预览用原文样本（用于流式分块着色）')
    segments: list[EmbeddingPreviewSegmentVo] = Field(default_factory=list)


class EmbeddingModelInfoVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    model_code: str = Field(..., description='模型编码')
    dimensions: int = Field(..., description='向量维度')
    provider: str | None = Field(default=None, description='提供商')


class EmbeddingStrategyVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    code: str
    name: str
    summary: str
    process_steps: list[str] = Field(default_factory=list, description='切分过程步骤（配置页展示）')
    applicable_scenes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    param_notes: list[str] = Field(default_factory=list, description='参数使用说明')
    param_schema: dict[str, Any] = Field(default_factory=dict)


class EmbeddingCreateTaskRespVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    task_id: int = Field(..., description='任务ID')


class EmbeddingTaskListQuery(BaseVo, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: str | None = Field(default=None, description='任务状态')
    source_type: str | None = Field(default=None, description='来源类型')
    doc_id: int | None = Field(default=None, description='文档ID')
    doc_title: str | None = Field(default=None, description='文档标题')
    begin_time: datetime | None = Field(default=None, description='开始时间')
    end_time: datetime | None = Field(default=None, description='结束时间')


class EmbeddingTaskListItemVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    task_id: int
    doc_id: int
    doc_title: str | None = None
    source_type: str | None = None
    split_type: str
    status: str
    release_tag: str | None = None
    chunk_count: int | None = 0
    embedded_count: int | None = 0
    embedding_model_code: str | None = None
    dimensions: int | None = None
    error_message: str | None = None
    create_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class EmbeddingTaskDetailVo(EmbeddingTaskListItemVo):
    split_params: dict[str, Any] | str | None = None


class EmbeddingSegmentListQuery(BaseVo, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    skip_embedding: int | None = Field(default=None, description='筛选 skip_embedding')


class EmbeddingSegmentVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    id: int
    task_id: int
    doc_id: int
    file_id: int
    chunk_id: str
    chunk_order: int
    text: str | None = None
    metadata: TextSegmentMetadataVo | None = Field(default=None, validation_alias='metadata_json')
    parent_chunk_id: str | None = None
    skip_embedding: int | None = 0
    embedding_id: str | None = None
    status: str | None = None
    release_tag: str
    create_time: datetime | None = None

    @field_validator('metadata', mode='before')
    @classmethod
    def _parse_metadata(cls, v: Any) -> Any:
        if v is None or v == '':
            return None
        if isinstance(v, TextSegmentMetadataVo):
            return v
        if isinstance(v, str):
            return TextSegmentMetadataVo.model_validate(json.loads(v))
        if isinstance(v, dict):
            return TextSegmentMetadataVo.model_validate(v)
        return v
