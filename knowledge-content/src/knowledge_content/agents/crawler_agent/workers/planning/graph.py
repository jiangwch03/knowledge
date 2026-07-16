"""
Planning 子 Agent — langchain create_agent

ReAct 循环、工具分发、轮次上限由 create_agent + ModelCallLimitMiddleware 内置处理。
动态 system prompt / 按 state 换模型见 agents/middleware/planning_middleware.py。
"""

from __future__ import annotations

import asyncio

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware
from langgraph.graph.state import CompiledStateGraph

from knowledge_common.agent.schema.context import AgentIdentityContext
from knowledge_common.config.env import CrawlerAgentConfig
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.middleware.crawler_model_middleware import crawler_model_middleware
from knowledge_content.agents.middleware.crawler_state_sync_middleware import (
    crawler_state_sync_middleware,
)
from knowledge_content.agents.middleware.planning_middleware import (
    planning_system_prompt,
)
from knowledge_content.agents.states.crawler_planning_state import PlanningState
from knowledge_content.agents.tools import CRAWL_AGENT_PLANNING_TOOLS
from knowledge_content.agents.utils.llm_util import get_base_chat_model

_planning_subgraph: CompiledStateGraph | None = None
_planning_build_lock = asyncio.Lock()


async def build_planning_subgraph() -> CompiledStateGraph:
    """构建 Planning create_agent 图（CompiledStateGraph，可直接作为 CompiledSubAgent runnable）"""
    default_model = await get_base_chat_model(None)
    max_rounds = CrawlerAgentConfig.crawler_agent_max_react_rounds

    graph = create_agent(
        model=default_model,
        tools=CRAWL_AGENT_PLANNING_TOOLS,
        state_schema=PlanningState,
        context_schema=AgentIdentityContext,
        middleware=[
            planning_system_prompt,
            crawler_model_middleware,
            crawler_state_sync_middleware,
            ModelCallLimitMiddleware(run_limit=max_rounds, exit_behavior='end'),
        ],
        name='planning_agent',
    )
    logger.info('[CrawlerAgent] Planning create_agent 构建完成 (run_limit={})', max_rounds)
    return graph


async def get_planning_subgraph() -> CompiledStateGraph:
    """Planning 子图单例"""
    global _planning_subgraph
    if _planning_subgraph is None:
        async with _planning_build_lock:
            if _planning_subgraph is None:
                _planning_subgraph = await build_planning_subgraph()
                logger.info('[CrawlerAgent] Planning 子图就绪')
    return _planning_subgraph
