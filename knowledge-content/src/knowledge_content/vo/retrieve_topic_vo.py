from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.vo.base_vo import BaseVo


class TopicSourceSegmentVo(BaseModel):
    """抽词用的分段。父块或没有父块的独立块。"""

    text: str | None = None
    parent_chunk_id: str | None = None
    skip_embedding: int | None = 0


class TopicKeywordWeightVo(BaseModel):
    """一个关键词及其权重。"""

    keyword: str
    weight: float


class RetrieveTopicKeywordVo(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    keyword: str
    weight: float


class RetrieveTopicListQuery(BaseVo, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    topic_name: str | None = Field(default=None, description='主题名称')


class RetrieveTopicListItemVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    topic_id: int
    topic_name: str
    description: str | None = None
    task_id: int
    doc_id: int
    doc_title: str | None = None
    keyword_count: int = 0
    status: str = 'GENERATING'
    error_message: str | None = None
    create_by: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class RetrieveTopicDetailVo(RetrieveTopicListItemVo):
    keywords: list[RetrieveTopicKeywordVo] = Field(default_factory=list)


class RetrieveTopicCreateRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    topic_name: str = Field(..., min_length=1, max_length=64, description='主题名称')
    description: str | None = Field(default=None, max_length=1000, description='主题描述')
    task_id: int = Field(..., description='切分任务')

    @field_validator('topic_name')
    @classmethod
    def strip_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError('主题名称不能为空')
        return name

    @field_validator('description')
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class RetrieveTopicUpdateRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    task_id: int = Field(..., description='切分任务')
    description: str | None = Field(default=None, max_length=1000, description='主题描述')
    keep_keywords: bool = Field(..., description='保留旧关键词')

    @field_validator('description')
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None
