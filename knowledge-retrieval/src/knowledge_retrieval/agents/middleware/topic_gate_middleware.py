"""主题闸门中间件：决定 prompt_profile（cs / knowledge）。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime

from knowledge_common.utils.log_util import logger
from knowledge_retrieval.agents.utils.message_util import last_human_text
from knowledge_retrieval.agents.utils.runtime_context_util import runtime_ctx_int
from knowledge_retrieval.service.topic_gate_service import TopicGateService


class TopicGateMiddleware(AgentMiddleware):
    """before_agent：按改写后问句路由 cs / knowledge。"""

    async def abefore_agent(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:
        # 幂等：before_agent 通常只在 invoke 入口跑一次；若入口重入且本轮已路由
        #（checkpoint resume / 同 thread 未清空 prompt_profile），则跳过，避免重复打闸门 LLM。
        # 正常 chat_stream 每轮会在 build_chat_input 里把 prompt_profile 置 ''。
        profile = str(state.get('prompt_profile') or '').strip()
        if profile:
            logger.info('[KnowledgeQA] skip topic_gate (already routed) profile={}', profile)
            return None

        # 优先 search_query（上游改写）；否则取最后一条用户消息。
        question = str(state.get('search_query') or '').strip() or last_human_text(state)
        if not question:
            return {'prompt_profile': 'cs'}

        model_id = runtime_ctx_int(runtime, 'model_id')
        gate = await TopicGateService.route(question, model_id=model_id)
        logger.info('[KnowledgeQA] topic_gate profile={}', gate.prompt_profile)
        return {'prompt_profile': gate.prompt_profile}


topic_gate_middleware = TopicGateMiddleware()
