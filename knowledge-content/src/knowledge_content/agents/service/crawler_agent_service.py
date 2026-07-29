"""
爬虫 Agent 对话编排

  - _CrawlerAgentService：继承 AgentChatService，注入图定义与 HITL 映射（内部实现）
  - CrawlerAgentService    ：对外入口，供 Controller 调用
"""

from collections.abc import AsyncIterator

from langgraph.graph.state import CompiledStateGraph

from knowledge_common.agent.enums.agent_type_enum import AgentType
from knowledge_common.agent.runtime.chat_service import AgentChatService
from knowledge_common.agent.runtime.sse import format_sse
from knowledge_common.agent.schema.chat_vo import AgentChatStreamVo, AgentResumeStreamVo
from knowledge_common.config.env import CrawlerAgentConfig
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_content.agents.crawler_agent.graph import get_root_graph
from knowledge_content.vo.crawler_vo import ChatMessageVo, ResumeVo


class _CrawlerAgentService(AgentChatService):
    """爬虫 Agent 运行时：图定义 + HITL interrupt 映射。"""

    agent_type = AgentType.WEB_CRAWLER.value

    @classmethod
    async def get_graph(cls) -> CompiledStateGraph:
        return await get_root_graph()

    @classmethod
    def format_hitl_user_choice_event(cls, hitl_request: dict) -> str | None:
        actions = hitl_request.get('action_requests') or []
        if not actions:
            return None

        first = actions[0]
        tool_name = first.get('name', '')
        description = first.get('description', '') or f'请确认执行工具 {tool_name}？'

        if tool_name == 'crawl_execute':
            interrupt_type = CrawlerAgentConfig.interrupt_strategy_confirmation
            title = '请确认提交正式爬取'
        elif tool_name == 'apply_scope_change':
            interrupt_type = CrawlerAgentConfig.interrupt_rescope_confirmation
            title = '请确认应用新爬取范围'
        else:
            interrupt_type = 'tool_approval'
            title = f'请确认执行 {tool_name}'

        return format_sse('user_choice', {
            'type': interrupt_type,
            'input_mode': 'choice',
            'title': title,
            'description': description,
            'choices': [
                {'value': 'approve', 'label': '确认'},
                {'value': 'reject', 'label': '取消'},
            ],
            'tool_name': tool_name,
            'action_requests': actions,
        })


class CrawlerAgentService:
    """爬虫 Agent 对外服务入口（Controller 调用）：聊天与审批。"""

    @classmethod
    async def stream_chat(
        cls,
        session_id: int,
        vo: ChatMessageVo,
        current_user: CurrentUserModel,
    ) -> AsyncIterator[str]:
        async for event in _CrawlerAgentService.chat_stream(
            AgentChatStreamVo(
                session_id=session_id,
                content=vo.content,
                current_user=current_user,
                model_id=vo.model_id,
            )
        ):
            yield event

    @classmethod
    async def stream_resume(
        cls,
        session_id: int,
        vo: ResumeVo,
        current_user: CurrentUserModel,
    ) -> AsyncIterator[str]:
        async for event in _CrawlerAgentService.resume_stream(
            AgentResumeStreamVo(
                session_id=session_id,
                resume_value=vo.resume_value,
                current_user=current_user,
            )
        ):
            yield event
