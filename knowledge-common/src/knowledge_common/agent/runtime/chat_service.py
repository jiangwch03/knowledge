"""
Agent 对话编排服务基类。

各业务 Agent 继承本类，注入图定义与 interrupt 映射；消息存储 / SSE 协议由 common 统一处理。
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, ClassVar

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from knowledge_common.agent.runtime.sse import format_sse
from knowledge_common.agent.runtime.stream_processor import AgentStreamProcessor
from knowledge_common.agent.schema.context import AgentIdentityContextVo
from knowledge_common.agent.schema.message_vo import AgentMessageVo
from knowledge_common.agent.service.agent_message_service import AgentMessageService
from knowledge_common.agent.service.agent_session_service import AgentSessionService
from knowledge_common.utils.log_util import logger


class AgentChatService(ABC):
    """Agent 对话编排基类：存消息 → 跑图 → 查中断。"""

    agent_type: ClassVar[str]
    hidden_supervisor_tools: ClassVar[frozenset[str]] = frozenset({'task'})

    @classmethod
    @abstractmethod
    async def get_graph(cls) -> CompiledStateGraph:
        """返回当前 Agent 的编译图。"""

    @classmethod
    def build_chat_input(cls, content: str) -> dict[str, Any]:
        """构建 chat_stream 本轮图输入。"""
        return {'messages': [HumanMessage(content=content)]}

    @classmethod
    @abstractmethod
    def format_hitl_user_choice_event(cls, hitl_request: dict) -> str | None:
        """将 deepagents HITL interrupt 映射为 user_choice SSE。"""

    @classmethod
    async def chat_stream(
        cls,
        session_id: int,
        content: str,
        user_id: int,
        dept_id: int | None,
        create_by: str,
        model_id: int | None = None,
    ) -> AsyncIterator[str]:
        logger.info(f'[Agent] 步骤1: 存储用户消息, session_id={session_id}')
        user_msg = await AgentMessageService.add_user_message(
            AgentMessageVo(
                session_id=session_id,
                content=content,
                user_id=user_id,
                dept_id=dept_id,
                create_by=create_by,
            )
        )

        logger.info('[Agent] 步骤2: 推送用户消息确认事件')
        yield format_sse('message', {'message_id': user_msg, 'role': 'user', 'content': content})

        try:
            compiled = await cls.get_graph()
            config = {'configurable': {'thread_id': str(session_id)}}
            input_or_resume = cls.build_chat_input(content)
            context = AgentIdentityContextVo(
                session_id=session_id,
                user_id=user_id,
                dept_id=dept_id,
                user_name=create_by,
                model_id=model_id,
            )

            async for event in AgentStreamProcessor(
                context,
                hidden_supervisor_tools=cls.hidden_supervisor_tools,
            ).run(compiled, config, input_or_resume):
                yield event

            async for event in cls._check_post_interrupt(compiled, config):
                yield event
        except Exception as e:
            logger.opt(exception=True).error('[Agent] chat_stream 执行异常: {}', e)
            yield format_sse('error', {'message': '[Agent] 对话执行异常,服务器异常,请联系运维处理'})

    @classmethod
    async def resume_stream(
        cls,
        session_id: int,
        resume_value: str,
        user_id: int,
        dept_id: int | None,
        create_by: str,
    ) -> AsyncIterator[str]:
        logger.info(f'[AgentResume] 开始处理中断恢复, session_id={session_id}, resume_value={resume_value}')

        try:
            compiled = await cls.get_graph()
            config = {'configurable': {'thread_id': str(session_id)}}

            state_snapshot = await compiled.aget_state(config)
            has_pending_interrupt = bool(
                state_snapshot
                and state_snapshot.tasks
                and any(t.interrupts for t in state_snapshot.tasks)
            )

            if not has_pending_interrupt:
                error_msg = (
                    f'[AgentResume] session_id={session_id} 调用 resume_stream 但无 pending interrupt，'
                    f'状态异常: resume_value={resume_value}'
                )
                logger.error(error_msg)
                yield format_sse('error', {'message': error_msg})
                return

            logger.info('[AgentResume] 有 pending interrupt，Command(resume={})', resume_value)
            input_or_resume = await cls._build_resume_command(compiled, config, resume_value)
            session = await AgentSessionService.get_session_vo(session_id, agent_type=cls.agent_type)
            context = AgentIdentityContextVo(
                session_id=session_id,
                user_id=user_id,
                dept_id=dept_id,
                user_name=create_by,
                model_id=session.model_id,
            )

            async for event in AgentStreamProcessor(
                context,
                hidden_supervisor_tools=cls.hidden_supervisor_tools,
            ).run(compiled, config, input_or_resume):
                yield event

            async for event in cls._check_post_interrupt(compiled, config):
                yield event
        except Exception as e:
            logger.opt(exception=True).error('[AgentResume] 中断恢复执行异常: {}', e)
            yield format_sse('error', {'message': '[AgentResume] 中断恢复异常,服务器异常,请联系运维处理'})

    @classmethod
    async def _check_post_interrupt(cls, compiled, config):
        post_state = await compiled.aget_state(config)
        if not post_state or not post_state.tasks:
            logger.info('[Agent] 步骤5: astream后无pending task')
            return

        logger.info('[Agent] 步骤5: astream后检查中断状态, tasks_count={}', len(post_state.tasks))
        for i, task in enumerate(post_state.tasks):
            interrupts = task.interrupts or ()
            logger.info(
                '[Agent] 步骤5: task#{}, interrupts_count={}, task_ns={}',
                i, len(interrupts), getattr(task, 'ns', 'N/A'),
            )
            for interrupt_info in interrupts:
                value = getattr(interrupt_info, 'value', interrupt_info)
                if not isinstance(value, dict):
                    logger.info('[Agent] 步骤5: 非dict类型中断, value_type={}', type(value).__name__)
                    continue

                if value.get('action_requests'):
                    event = cls.format_hitl_user_choice_event(value)
                    if event:
                        yield event
                    continue

                logger.info(
                    '[Agent] 步骤5: 未映射的 interrupt type={} keys={}',
                    value.get('type', 'N/A'),
                    list(value.keys()),
                )

    @classmethod
    async def _get_pending_interrupt_value(cls, compiled, config) -> dict | None:
        post_state = await compiled.aget_state(config)
        if not post_state or not post_state.tasks:
            return None
        for task in post_state.tasks:
            for interrupt_info in task.interrupts or ():
                value = getattr(interrupt_info, 'value', interrupt_info)
                if isinstance(value, dict):
                    return value
        return None

    @classmethod
    async def _build_resume_command(cls, compiled, config, resume_value: str) -> Command:
        pending = await cls._get_pending_interrupt_value(compiled, config)
        if not pending:
            return Command(resume=resume_value)

        if pending.get('action_requests'):
            count = len(pending['action_requests'])
            if resume_value.strip().lower() == 'approve':
                decisions = [{'type': 'approve'} for _ in range(count)]
            else:
                # 明确告知 LLM：拒绝是用户否决，不是瞬态失败，禁止同工具立刻重提
                decisions = [{
                    'type': 'reject',
                    'message': (
                        '用户已明确拒绝/取消该操作。这不是系统错误或超时，'
                        '禁止再次调用同一工具重试。请告知用户已取消，'
                        '并等待其明确说明下一步（改方案、换网址或结束）。'
                    ),
                } for _ in range(count)]
            logger.info('[AgentResume] HITL resume decisions_count={}', count)
            return Command(resume={'decisions': decisions})

        return Command(resume=resume_value.strip().lower())
