from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AgentSessionVo(BaseModel):
    """Agent 会话响应 VO。"""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    session_id: int = Field(..., description='会话ID')
    session_title: str | None = Field(default=None, description='会话标题')
    status: str = Field(..., description='会话状态')
    model_id: int | None = Field(default=None, description='选择的模型ID')
    create_time: datetime = Field(..., description='创建时间')
    update_time: datetime | None = Field(default=None, description='更新时间')
