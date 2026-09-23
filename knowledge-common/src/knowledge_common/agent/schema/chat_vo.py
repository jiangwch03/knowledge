"""Agent 对话流式编排入参 VO。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from knowledge_common.vo.user_vo import CurrentUserModel


class AgentChatStreamVo(BaseModel):
    """chat_stream 入参。"""

    session_id: int = Field(gt=0, description='会话ID')
    content: str = Field(min_length=1, description='用户消息内容')
    current_user: CurrentUserModel = Field(description='当前登录用户')
    model_id: int | None = Field(default=None, description='模型ID')
    release_tag: str | None = Field(
        default=None,
        description='仅知识问答检索使用的发布标签（canary/prod），空则问答默认 prod；其他 Agent 忽略',
    )
    task_id: int | None = Field(
        default=None,
        description='仅知识问答检索使用，按 embedding 任务过滤；其他 Agent 忽略',
    )

    @property
    def user_id(self) -> int:
        return int(self.current_user.user.user_id)

    @property
    def dept_id(self) -> int | None:
        return self.current_user.user.dept_id

    @property
    def create_by(self) -> str:
        return self.current_user.user.user_name or ''


class AgentResumeStreamVo(BaseModel):
    """resume_stream 入参。"""

    session_id: int = Field(gt=0, description='会话ID')
    resume_value: str = Field(min_length=1, description='中断恢复值')
    current_user: CurrentUserModel = Field(description='当前登录用户')

    @property
    def user_id(self) -> int:
        return int(self.current_user.user.user_id)

    @property
    def dept_id(self) -> int | None:
        return self.current_user.user.dept_id

    @property
    def create_by(self) -> str:
        return self.current_user.user.user_name or ''
