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
from knowledge_common.agent.service.agent_message_service import AgentMessageService
from knowledge_common.config.env import AiModelFunctionAdapterConfig, CrawlerAgentConfig
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
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
    """爬虫 Agent 对外服务入口（Controller 调用）。"""

    @classmethod
    async def get_crawler_models(cls) -> list[AiModelConfigModel]:
        return await AiModelFunctionAdapterDao.get_adapters_by_param_id(
            AiModelFunctionAdapterConfig.crawler_agent_param_id
        )

    @classmethod
    async def stream_chat(
        cls,
        session_id: int,
        vo: ChatMessageVo,
        current_user: CurrentUserModel,
    ) -> AsyncIterator[str]:
        user = current_user.user
        async for event in _CrawlerAgentService.chat_stream(
            session_id=session_id,
            content=vo.content,
            user_id=user.user_id,
            dept_id=user.dept_id,
            create_by=user.user_name,
            model_id=vo.model_id,
        ):
            yield event

    @classmethod
    async def stream_resume(
        cls,
        session_id: int,
        vo: ResumeVo,
        current_user: CurrentUserModel,
    ) -> AsyncIterator[str]:
        user = current_user.user
        async for event in _CrawlerAgentService.resume_stream(
            session_id=session_id,
            resume_value=vo.resume_value,
            user_id=user.user_id,
            dept_id=user.dept_id,
            create_by=user.user_name,
        ):
            yield event

    @classmethod
    async def get_messages(
        cls,
        session_id: int,
        page_num: int = 1,
        page_size: int = 50,
    ):
        return await AgentMessageService.get_messages(
            session_id=session_id,
            page_num=page_num,
            page_size=page_size,
        )
