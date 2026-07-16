"""
Agent context schema 定义
"""

from typing import Any, Mapping, TypedDict

from knowledge_common.exceptions.exception import ServiceException
from pydantic import BaseModel, Field

class ModelIdContext(TypedDict):
    """
    Model ID 上下文
    """
    model_id: int | None

class AgentIdentityContext(ModelIdContext):
    """
    Agent 身份/审计上下文

    用于聚合会话与操作者身份，推荐由上游入口一次性注入。
    """

    session_id: int
    user_id: int
    dept_id: int | None
    user_name: str


class ModelIdContextVo(BaseModel):
    """Model ID 上下文 VO"""
    model_id: int | None = Field(default=None, description='模型ID')

class AgentIdentityContextVo(ModelIdContextVo):
    """Agent 身份/审计上下文 VO"""

    session_id: int = Field(description='会话ID')
    user_id: int = Field(description='用户ID')
    dept_id: int | None = Field(default=None, description='部门ID')
    user_name: str = Field(description='用户登录名')

    @classmethod
    def from_state(cls, state: Mapping[str, Any]) -> 'AgentIdentityContextVo':
        """
        从 Agent state 中提取 context 并封装为 VO。

        约定 state 结构:
            {
              "context": {
                "session_id": ...,
                "user_id": ...,
                "dept_id": ...,
                "user_name": ...
              }
            }
        """
        context = state.get('context')
        if not isinstance(context, Mapping):
            raise ValueError('state 中缺少 context 或 context 结构非法')
        return cls.model_validate(context)


def get_agent_identity_context_vo(payload: Mapping[str, Any]) -> AgentIdentityContextVo:
    """
    获取 Agent 身份上下文 VO。

    支持两种入参:
    1) 传入完整 state（包含 context）
    2) 直接传入 context 字典
    """
    # 从 state 中提取 context
    context = payload.get('context')
    if isinstance(context, Mapping):
        return AgentIdentityContextVo.model_validate(context)
        
    # 直接传入 context 字典
    return AgentIdentityContextVo.model_validate(payload)


def get_agent_identity_from_tool_runtime(runtime: Any) -> AgentIdentityContextVo:
    """
    从 ToolRuntime.context 提取身份上下文。

    身份字段（session_id/user_id/dept_id/user_name/model_id）由入口
    astream(..., context=...) 单次注入，工具通过 ToolRuntime 直接读取。
    """
    if runtime is None:
        raise ServiceException('缺少 ToolRuntime')
        
    context = getattr(runtime, 'context', None)

    if context is None:
        raise ServiceException('缺少 runtime context')

    payload = context.model_dump() if hasattr(context, 'model_dump') else context
    return get_agent_identity_context_vo(payload)
