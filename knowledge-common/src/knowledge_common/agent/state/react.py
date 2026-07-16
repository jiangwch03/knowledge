"""
ReAct Agent 基础状态

所有 ReAct Agent 的 LangGraph State 应继承此类，
统一 messages / react_round 字段语义。
"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ReactBaseState(TypedDict):
    """
    ReAct Agent 基础状态

    提供 ReAct 循环所需的最小状态字段集。
    各业务 Agent 的 TypedDict State 应继承此类并扩展业务字段。

    Attributes:
        messages: 对话消息列表（user/assistant/tool/system），
                  通过 add_messages reducer 自动追加，LangGraph 核心数据载体
        react_round: 当前 ReAct 轮次计数，由 analyze_node 递增，
                     达到业务方配置的上限后停止工具调用
    """

    messages: Annotated[list[BaseMessage], add_messages]
    react_round: int
