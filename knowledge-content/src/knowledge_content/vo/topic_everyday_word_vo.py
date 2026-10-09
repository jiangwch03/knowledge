from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.vo.base_vo import BaseVo


class TopicEverydayWordQuery(BaseVo, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    word: str | None = Field(default=None, description='日常词，模糊匹配')
    lang: str | None = Field(default=None, description='语种 zh中文 en英文')
    word_class: str | None = Field(default=None, description='词类 noun/verb/adj/function/other')
    source: str | None = Field(default=None, description='来源 zh_idf中文词频表 en_common常用英语 manual手工录入')


class TopicEverydayWordVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    word_id: int
    word: str
    lang: str = 'zh'
    word_class: str = 'other'
    source: str = 'manual'
    update_time: datetime | None = None


class TopicEverydayWordAddRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    word: str = Field(..., min_length=1, max_length=64, description='要加入的日常词')


class TopicEverydayWordRemoveRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    word_ids: list[int] = Field(..., min_length=1, max_length=500, description='要剔除的日常词')
