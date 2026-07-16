"""
网页爬取 Agent 图入口（直接使用 deepagents Supervisor）。

当前不再额外包父图：
  - Checkpointer 直接绑定在 deepagents Supervisor；
  - 面客协议转换、消息落库、resume 映射等由 service 层负责。
"""

from langgraph.graph.state import CompiledStateGraph

from knowledge_content.agents.crawler_agent.workers.supervisor.deep_agent import (
    get_deep_supervisor_graph,
)

async def get_root_graph() -> CompiledStateGraph:
    """获取 deepagents Supervisor（该层仅做中转）。"""
    return await get_deep_supervisor_graph()
