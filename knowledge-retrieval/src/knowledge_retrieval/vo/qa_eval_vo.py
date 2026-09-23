"""评测非流式问答采数 VO。"""

from typing import Literal

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank

from knowledge_common.vo.base_vo import BaseVo
from knowledge_retrieval.enums.release_tag_enum import ReleaseTag

ReleaseQueryTag = Literal[ReleaseTag.CANARY, ReleaseTag.PROD]


class EvalAnswerRequestVo(BaseVo):
    """评测非流式采数请求。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    question: str = Field(..., min_length=1, description='评测问题')
    release_tag: ReleaseQueryTag = Field(
        default=ReleaseTag.CANARY,
        description='发布标签，只能是 canary 或 prod，默认 canary',
    )
    task_id: int | None = Field(default=None, description='embedding 任务 ID')
    model_id: int | None = Field(default=None, gt=0, description='可选模型 ID')

    @NotBlank(field_name='question', message='问题不能为空')
    def get_question(self) -> str:
        return self.question


class EvalAnswerRespVo(BaseVo):
    """评测非流式采数响应。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    answer: str = Field(default='', description='模型回答')
    contexts: list[str] = Field(default_factory=list, description='检索上下文文本列表')
    release_tag: ReleaseQueryTag = Field(
        default=ReleaseTag.CANARY,
        description='本次检索使用的发布标签，与请求一致',
    )
    task_id: int | None = Field(default=None, description='本次检索使用的 embedding 任务 ID，与请求一致')
