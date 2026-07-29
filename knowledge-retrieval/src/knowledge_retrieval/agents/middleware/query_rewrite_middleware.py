"""查询改写中间件：口语规范化 / 指代消解，写入 search_query，并同步本轮 HumanMessage。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from knowledge_common.utils.log_util import logger
from knowledge_retrieval.agents.utils.message_util import last_human_message, message_text
from knowledge_retrieval.agents.utils.runtime_context_util import runtime_ctx_int
from knowledge_retrieval.service.query_rewrite_service import QueryRewriteService
from knowledge_retrieval.vo.query_rewrite_vo import QueryRewriteRequestVo


class QueryRewriteMiddleware(AgentMiddleware):
    """before_agent：改写本轮用户问句，供检索与回答 LLM 共用。

    同步改写 checkpointer 内本轮 HumanMessage，使后续路由/检索/生成与压缩同源。
    聊天列表不受影响：用户原文在跑图前已入库并 SSE 推送。
    """

    async def abefore_agent(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:
        # 幂等：before_agent 在单次 invoke 内通常只跑入口一次，不会随 model/tool 循环重复。
        # 但若入口被重入且本轮已写入 search_query（如 checkpoint resume 又从入口进来、
        # 或图被同 thread 再次 invoke 且未清空该字段），则跳过，避免重复打改写 LLM。
        # 正常 chat_stream 每轮会在 build_chat_input 里把 search_query 置 ''，此分支不触发。
        if str(state.get('search_query') or '').strip():
            return None

        last_human = last_human_message(state)
        question = message_text(last_human)
        if not question:
            return {'search_query': ''}

        # session_id 用于拉历史做指代消解；model_id 指定改写所用模型
        rewritten = await QueryRewriteService.rewrite(
            QueryRewriteRequestVo(
                question=question,
                session_id=runtime_ctx_int(runtime, 'session_id'),
                model_id=runtime_ctx_int(runtime, 'model_id'),
            )
        )
        logger.info('[KnowledgeQA] query_rewrite done len={}', len(rewritten))
        update: dict[str, Any] = {'search_query': rewritten}
        # 同 id 走 add_messages 覆盖，避免追加第二条 HumanMessage
        if rewritten != question and last_human is not None:
            patched = self._patch_human_content(last_human, rewritten)
            if patched is not None:
                update['messages'] = [patched]
        return update

    def _patch_human_content(self, msg: Any, content: str) -> HumanMessage | None:
        """保留原 message id，供 add_messages 原地覆盖。"""
        msg_id = msg.get('id') if isinstance(msg, dict) else getattr(msg, 'id', None)
        if not msg_id:
            logger.warning('[KnowledgeQA] query_rewrite skip messages patch: missing message id')
            return None
        return HumanMessage(content=content, id=msg_id)


query_rewrite_middleware = QueryRewriteMiddleware()
