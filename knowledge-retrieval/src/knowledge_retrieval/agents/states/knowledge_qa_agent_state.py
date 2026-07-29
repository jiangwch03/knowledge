from __future__ import annotations

from typing import NotRequired

from langchain.agents import AgentState


class KnowledgeQaAgentState(AgentState):
    """知识问答 Agent 状态：改写 / 路由 / 检索（均由 before_agent 中间件写入）。"""

    # ================================ 改写相关 ================================
    # 改写后的检索问句（本轮 HumanMessage 同步为同文，供 LLM/压缩）
    search_query: NotRequired[str]  
    
    # ================================ 路由相关 ================================
    # cs=客服 / knowledge=知识问答（兼作是否混合检索）；空串表示本轮待路由
    prompt_profile: NotRequired[str]  

    # ================================ 检索相关 ================================
    # 混合检索命中结果
    retrieve_hits: NotRequired[list[dict]]  
     # 本轮检索是否已完成（避免重复检索）
    retrieve_done: NotRequired[bool] 
