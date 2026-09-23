"""知识问答 Agent 编排：单图 AgentChatService（改写/路由/检索均在图内中间件）。"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from knowledge_common.agent.enums.agent_type_enum import AgentType
from knowledge_common.agent.runtime.chat_service import AgentChatService
from knowledge_common.agent.schema.chat_vo import AgentChatStreamVo
from knowledge_common.agent.schema.context import AgentIdentityContextVo
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.agents.knowledge_qa_agent.graph import get_knowledge_qa_graph
from knowledge_retrieval.agents.states.knowledge_qa_agent_state import KnowledgeQaAgentState
from knowledge_retrieval.enums.release_tag_enum import ReleaseTag
from knowledge_retrieval.vo.knowledge_qa_vo import ChatMessageVo
from knowledge_retrieval.vo.qa_eval_vo import EvalAnswerRequestVo, EvalAnswerRespVo


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
    def build_chat_input(
        cls,
        content: str,
        *,
        release_tag: str | None = None,
        task_id: int | None = None,
        **_: Any,
    ) -> dict[str, Any]:
        # checkpointer 会保留上轮路由/检索字段，每轮显式清空，由中间件重算
        return {
            'messages': [HumanMessage(content=content)],
            'search_query': '',
            'prompt_profile': '',
            'retrieve_hits': [],
            'retrieve_done': False,
            'release_tag': release_tag or ReleaseTag.PROD.value,
            'task_id': task_id,
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
                release_tag=vo.release_tag,
                task_id=vo.task_id,
            )
        ):
            yield event

    @classmethod
    async def eval_answer(
        cls,
        vo: EvalAnswerRequestVo,
        current_user: CurrentUserModel,
    ) -> EvalAnswerRespVo:
        """非流式评测出口：跑同一套 Agent 图，返回 answer + contexts。"""
        release_tag = vo.release_tag.value
        compiled = await _KnowledgeQaAgentService.get_graph()
        thread_id: str = f'eval-{uuid.uuid4().hex}'
        config = {'configurable': {'thread_id': thread_id}}
        context = AgentIdentityContextVo(
            session_id=0,
            user_id=int(current_user.user.user_id),
            dept_id=current_user.user.dept_id,
            user_name=current_user.user.user_name or '',
            model_id=vo.model_id,
        )
        input_state = _KnowledgeQaAgentService.build_chat_input(
            vo.question,
            release_tag=release_tag,
            task_id=vo.task_id,
        )
        state: KnowledgeQaAgentState = await compiled.ainvoke(
            input_state,
            config=config,
            context=context.model_dump(),
        )
        last = state['messages'][-1]
        content = last.content
        answer = content.strip() if isinstance(content, str) else ''
        contexts = [str(hit['text']) for hit in state['retrieve_hits'] if hit.get('text')]
        return EvalAnswerRespVo(
            answer=answer,
            contexts=contexts,
            release_tag=state['release_tag'],
            task_id=state.get('task_id'),
        )
