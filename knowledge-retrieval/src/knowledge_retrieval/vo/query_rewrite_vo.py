from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class QueryRewriteRequestVo(BaseModel):
    """查询改写请求。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    question: str = Field(..., description='当前用户问题')
    session_id: int | None = Field(default=None, description='会话 ID，history 为空时用于拉取近期对话')
    history: list[Any] | None = Field(
        default=None,
        description='近期 human/ai 消息；None 且带 session_id 时由服务侧加载，[] 表示无历史',
    )
    model_id: int | None = Field(default=None, description='改写所用模型 ID')
