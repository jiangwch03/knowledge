"""知识问答 Agent 编排：单图 AgentChatService（改写/路由/检索均在图内中间件）。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from knowledge_common.agent.enums.agent_type_enum import AgentType
from knowledge_common.agent.runtime.chat_service import AgentChatService
from knowledge_common.agent.schema.chat_vo import AgentChatStreamVo
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.agents.knowledge_qa_agent.graph import get_knowledge_qa_graph
from knowledge_retrieval.vo.knowledge_qa_vo import ChatMessageVo


class _KnowledgeQaAgentService(AgentChatService):
    agent_type = AgentType.KNOWLEDGE_QA.value
    # 增量：与父类 skip_token_nodes 并集；屏蔽改写/闸门嵌套 LLM 的打字机泄漏
    skip_token_nodes = frozenset({
        'QueryRewriteMiddleware.before_agent',
        'TopicGateMiddleware.before_agent',
    })

    @classmethod
    async def get_graph(cls) -> CompiledStateGraph:
        return await get_knowledge_qa_graph()

    @classmethod
    def build_chat_input(cls, content: str) -> dict[str, Any]:
        # checkpointer 会保留上轮路由/检索字段，每轮显式清空，由中间件重算
        return {
            'messages': [HumanMessage(content=content)],
            'search_query': '',
            'prompt_profile': '',
            'retrieve_hits': [],
            'retrieve_done': False,
        }

    @classmethod
    def format_hitl_user_choice_event(cls, hitl_request: dict) -> str | None:
        return None


class KnowledgeQaAgentService:
    @classmethod
    async def stream_chat(
        cls,
        session_id: int,
        vo: ChatMessageVo,
        current_user: CurrentUserModel,
    ) -> AsyncIterator[str]:
        async for event in _KnowledgeQaAgentService.chat_stream(
            AgentChatStreamVo(
                session_id=session_id,
                content=vo.content,
                current_user=current_user,
                model_id=vo.model_id,
            )
        ):
            yield event
