"""knowledge-retrieval 评测采数跨服务 VO。

提供者：knowledge-retrieval
消费者：knowledge-admin（禁止在子项目重复定义）
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class EvalQaAnswerVo(BaseModel):
    """内部评测采数：答案 + 上下文。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    answer: str = ''
    contexts: list[str] = Field(default_factory=list)
