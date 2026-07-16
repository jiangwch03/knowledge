"""Agent 消息创建 VO（服务层）"""

from pydantic import BaseModel, Field


class AgentMessageVo(BaseModel):
    """封装创建 Agent 消息所需的全部参数。"""

    session_id: int = Field(gt=0, description='关联的聊天会话ID')
    content: str = Field(min_length=1, description='消息内容')
    user_id: int = Field(gt=0, description='用户ID')
    dept_id: int | None = Field(default=None, gt=0, description='部门ID')
    create_by: str | None = Field(default=None, description='创建者（登录名）')
    update_by: str | None = Field(default=None, description='更新者（登录名）')
    tool_call_id: str | None = Field(default=None, description='工具调用ID（role=tool时使用）')
    tool_name: str | None = Field(default=None, description='工具名称（role=tool时使用）')
    remark: str | None = Field(default=None, description='备注（子图消息存 source/agent_ns JSON）')
