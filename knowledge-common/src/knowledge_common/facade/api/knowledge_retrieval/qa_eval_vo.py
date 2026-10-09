"""knowledge-retrieval 评测采数跨服务 VO。

提供者：knowledge-retrieval
消费者：knowledge-admin（禁止在子项目重复定义）
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from knowledge_common.vo.base_vo import BaseVo


class EvalQaAnswerRequestVo(BaseVo):
    """内部评测采数请求（对齐 retrieval EvalAnswerRequestVo）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    question: str = Field(..., min_length=1, description='评测问题')
    user_id: int = Field(..., gt=0, description='操作者用户 ID，检索侧据此加载用户与数据范围')
    release_tag: str = Field(default='canary', description='发布标签 canary/prod')
    task_id: int | None = Field(default=None, description='embedding 任务 ID')
    model_id: int | None = Field(default=None, description='可选模型 ID')


class EvalQaAnswerVo(BaseModel):
    """内部评测采数：答案 + 上下文。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    answer: str = ''
    contexts: list[str] = Field(default_factory=list)
    release_tag: str | None = None
    task_id: int | None = None

    @field_validator('contexts', mode='before')
    @classmethod
    def _coerce_contexts(cls, value: object) -> object:
        if isinstance(value, str):
            return [value]
        return value
