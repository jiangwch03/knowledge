from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AgentMessageRespVo(BaseModel):
    """Agent 消息响应 VO。"""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    message_id: int = Field(..., description='消息ID')
    session_id: int = Field(..., description='关联会话ID')
    role: str = Field(..., description='消息角色 human/ai/system/tool/business')
    content: str | None = Field(default=None, description='消息内容')
    tool_call_id: str | None = Field(default=None, description='工具调用ID')
    tool_name: str | None = Field(default=None, description='工具名称')
    remark: str | None = Field(default=None, description='备注（子图消息存 source/agent_ns JSON）')
    create_time: datetime = Field(..., description='创建时间')
