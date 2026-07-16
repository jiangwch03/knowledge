"""Supervisor 子图专用状态"""

from typing import Annotated

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from knowledge_content.agents.states.crawler_agent_state import CrawlerAgentState


class SupervisorState(CrawlerAgentState):
    """
    Supervisor 子图状态

    继承 CrawlerAgentState 全部业务字段 + messages。
    子图 messages 独立管理。
    """

    messages: Annotated[list[BaseMessage], add_messages]
