"""条件混合检索中间件：prompt_profile=knowledge 时调用 DocumentVectorRetrieveService，并推送 citations SSE。"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from knowledge_common.agent.schema.business_stream_vo import BusinessStreamMessageVo
from knowledge_common.common.context import RequestContext
from knowledge_common.config.env import KnowledgeQaConfig
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.agents.utils.message_util import last_human_text
from knowledge_retrieval.service.document_vector_retrieve_service import DocumentVectorRetrieveService
from knowledge_retrieval.vo.document_vector_retrieve_vo import (
    DocumentVectorRetrieveRequestVo,
    DocumentVectorRetrieveResponseVo,
)


class HybridRetrieveMiddleware(AgentMiddleware):
    """before_agent：knowledge 路径执行混合检索，写入 retrieve_hits。"""

    async def abefore_agent(self, state: dict[str, Any], runtime: Runtime) -> dict[str, Any] | None:
        # 幂等：before_agent 通常只在 invoke 入口跑一次；若入口重入且本轮已检索过
        #（checkpoint resume / 同 thread 未清空 retrieve_done），则跳过，避免重复检索。
        # 正常 chat_stream 每轮会在 build_chat_input 里把 retrieve_done 置 False。

        # 非知识路径不检索；hits 已由 build_chat_input 清空，不置 retrieve_done
        if state.get('prompt_profile') != 'knowledge':
            logger.info('[KnowledgeQA] skip hybrid_retrieve (profile={})', state.get('prompt_profile'))
            return None

        # 本轮检索是否已完成（避免重复检索）
        if state.get('retrieve_done'):
            logger.info('[KnowledgeQA] skip hybrid_retrieve (already done)')
            return None

        # 优先 search_query（上游改写）；否则取最后一条用户消息。
        query: str = str(state.get('search_query') or '').strip() or last_human_text(state)
        if not query:
            return {'retrieve_hits': [], 'retrieve_done': True}

        # 数据权限依赖完整登录用户（含 role.data_scope）；拿不到直接抛，不兜底
        current_user: CurrentUserModel = RequestContext.get_current_user()
        request: DocumentVectorRetrieveRequestVo = DocumentVectorRetrieveRequestVo(
            query=query,
            top_k=KnowledgeQaConfig.knowledge_qa_retrieve_top_k,
            score_threshold=KnowledgeQaConfig.knowledge_qa_retrieve_score_threshold,
            enable_rerank=KnowledgeQaConfig.knowledge_qa_retrieve_enable_rerank,
            rrf_k=KnowledgeQaConfig.knowledge_qa_retrieve_rrf_k,
        )
        try:
            result: DocumentVectorRetrieveResponseVo = await DocumentVectorRetrieveService.hybrid_retrieve(
                request, current_user
            )
            # 业务 HitVo → camelCase dict：写入 state / business SSE / 落库
            hits: list[dict[str, Any]] = [h.model_dump(by_alias=True) for h in result.hits]
            logger.info('[KnowledgeQA] hybrid_retrieve hits={}', len(hits))
            self._emit_citations(
                {
                    'searchQuery': query,  # 本轮实际检索词（改写后优先）
                    'hits': hits,  # 检索命中列表（含 docId/chunkId/text 等）
                }
            )
            return {'retrieve_hits': hits, 'retrieve_done': True}
        except Exception as exc:
            logger.opt(exception=True).warning('[KnowledgeQA] hybrid_retrieve 失败，继续无资料回答: {}', exc)
            self._emit_citations(
                {
                    'searchQuery': query,  # 本轮实际检索词
                    'hits': [],  # 失败时无命中
                    'error': str(exc),  # 失败原因（供前端/排查）
                }
            )
            return {'retrieve_hits': [], 'retrieve_done': True}

    def _emit_citations(self, payload: dict[str, Any]) -> None:
        try:
            writer = get_stream_writer()
            writer(
                BusinessStreamMessageVo(
                    persist=True,
                    push_sse=True,
                    data=payload,
                ).model_dump()
            )
        except Exception as exc:
            # 无业务 SSE 旁路（单测/ainvoke 未开 custom stream_mode）时静默跳过
            logger.debug('[KnowledgeQA] citations stream skip: {}', exc)


hybrid_retrieve_middleware = HybridRetrieveMiddleware()
