"""知识问答单 Agent 图（create_agent + 改写/路由/检索中间件 + Tavily）。"""

from __future__ import annotations

import threading

from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph

from knowledge_common.agent.enums.agent_type_enum import AgentType
from knowledge_common.agent.memory.short_memory.checkpointer import Checkpointer
from knowledge_common.agent.schema.context import AgentIdentityContext
from knowledge_retrieval.agents.states.knowledge_qa_agent_state import KnowledgeQaAgentState
from knowledge_retrieval.agents.middleware.hybrid_retrieve_middleware import hybrid_retrieve_middleware
from knowledge_retrieval.agents.middleware.qa_prompt_middleware import qa_prompt_model_middleware
from knowledge_retrieval.agents.middleware.query_rewrite_middleware import query_rewrite_middleware
from knowledge_retrieval.agents.middleware.topic_gate_middleware import topic_gate_middleware
from knowledge_retrieval.agents.tools.tavily_search import tavily_search
from knowledge_retrieval.agents.utils.llm_util import get_base_chat_model

_graph: CompiledStateGraph | None = None
_lock = threading.Lock()


async def get_knowledge_qa_graph() -> CompiledStateGraph:
    """懒加载并缓存知识问答 Agent 图（双重检查锁，进程内单例）。

    中间件顺序（before_agent → wrap_model_call）：
      1. query_rewrite  — 口语规范化 / 指代消解 → search_query，并覆盖本轮 HumanMessage
      2. topic_gate     — 路由 cs / knowledge（knowledge 才检索）
      3. hybrid_retrieve — knowledge 路径混合检索，写入 retrieve_hits 并推送 citations
      4. qa_prompt      — 按 profile 切换系统提示，注入检索资料；可换模型
    工具：tavily_search（知识库不足时补网页来源）。
    """
    global _graph
    # 无锁快路径：已初始化则直接返回
    if _graph is not None:
        return _graph
    with _lock:
        # 锁内再判一次，避免并发下重复 create_agent
        if _graph is not None:
            return _graph
        model = await get_base_chat_model(None)
        checkpointer = await Checkpointer.get_checkpointer()
        _graph = create_agent(
            model=model,
            tools=[tavily_search],
            # 占位 system_prompt；实际提示由 qa_prompt_model_middleware 按 profile 覆盖
            system_prompt='你是知识库助手。',
            middleware=[
                query_rewrite_middleware,      # 改写 → search_query + 本轮 HumanMessage
                topic_gate_middleware,         # 路由 cs / knowledge
                hybrid_retrieve_middleware,    # knowledge 路径混合检索 → retrieve_hits + citations
                qa_prompt_model_middleware,    # 按 profile 切提示并注入检索资料；可换模型
            ],
            state_schema=KnowledgeQaAgentState,
            context_schema=AgentIdentityContext,  # 单次 invoke 身份上下文（session/user/model）
            checkpointer=checkpointer,  # 短记忆 / 多轮 resume
            name=AgentType.KNOWLEDGE_QA.value,
        )
        return _graph
