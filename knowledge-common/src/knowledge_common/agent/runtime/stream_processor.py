"""
Agent 流式事件处理器：把归一化事件流翻译成 SSE 并完成消息落库。
"""

import asyncio
import json
from typing import Any

from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from knowledge_common.agent.enums.sse_event_enum import AgentSseEvent, AgentToolCallPhase
from knowledge_common.agent.runtime.sse import format_sse
from knowledge_common.agent.schema.context import AgentIdentityContextVo
from knowledge_common.agent.schema.message_vo import AgentMessageVo
from knowledge_common.agent.service.agent_message_service import AgentMessageService
from knowledge_common.agent.stream import (
    SOURCE_SUBAGENT,
    SOURCE_SUPERVISOR,
    AITextEvent,
    HumanMessageEvent,
    NormalizedEvent,
    SystemMessageEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
    normalize_astream,
)
from knowledge_common.agent.utils.sensitive_mask_util import mask_sensitive_text
from knowledge_common.utils.log_util import logger


class AgentStreamProcessor:
    """
    消费 common 归一化事件流，翻译成 SSE 并完成消息落库。

    TokenEvent 只推前端打字机，不落库；其它 updates 事件落库 / 推工具卡片。
    父图逐条落库；子图只缓冲 updates，收敛时按序落库。
    """

    _SKIP_UPDATE_NODES = frozenset({'PatchToolCallsMiddleware.before_agent'})
    _HIDDEN_SUPERVISOR_TOOLS = frozenset({'task'})

    def __init__(
        self,
        context: AgentIdentityContextVo,
        *,
        hidden_supervisor_tools: frozenset[str] | None = None,
    ):
        self._ctx = context
        self._hidden_supervisor_tools = hidden_supervisor_tools or self._HIDDEN_SUPERVISOR_TOOLS
        self._subgraph_messages: dict[str, list[dict[str, Any]]] = {}

    async def run(self, compiled: CompiledStateGraph, config: dict, input_or_resume: Command | dict):
        try:
            logger.info('[Agent] 开始流式执行 astream')
            async for event in normalize_astream(
                compiled,
                config=config,
                context=self._ctx.model_dump(),
                input_or_resume=input_or_resume,
                skip_update_nodes=self._SKIP_UPDATE_NODES,
            ):
                await self._flush_subgraph_on_ns_change(event)
                for sse in await self._handle_event(event):
                    yield sse
            await self._flush_all_subgraphs()
            logger.info('[Agent] astream 执行完毕')
        except asyncio.CancelledError:
            logger.warning('[Agent] SSE 连接被客户端断开，任务已取消')
            return
        except Exception as e:
            logger.opt(exception=True).error('[Agent] 对话执行异常: {}', e)
            yield format_sse('error', {'message': '[Agent] 对话执行异常,服务器异常,请联系运维处理'})

    async def _handle_event(self, event: NormalizedEvent) -> list[str]:
        await self._persist(event)
        return self._sse(event)

    async def _persist(self, event: NormalizedEvent) -> None:
        if event.source == SOURCE_SUBAGENT:
            await self._persist_subagent(event)
            return
        await self._persist_supervisor(event)

    async def _persist_subagent(self, event: NormalizedEvent) -> None:
        if not event.agent_ns:
            return
        if isinstance(event, TokenEvent):
            return

        messages = self._subgraph_messages.setdefault(event.agent_ns, [])

        if isinstance(event, AITextEvent):
            text = (event.content or '').rstrip()
            if text:
                messages.append({'role': 'ai', 'content': text})
            return

        if isinstance(event, ToolCallEvent):
            messages.append({
                'role': 'tool',
                'tool_call_id': event.tool_call_id,
                'tool_name': event.tool_name,
                'tool_args': event.tool_args,
                'result': None,
            })
            return

        if isinstance(event, ToolResultEvent):
            for item in reversed(messages):
                if item.get('role') == 'tool' and item.get('tool_call_id') == event.tool_call_id:
                    item['result'] = event.content
                    return
            messages.append({
                'role': 'tool',
                'tool_call_id': event.tool_call_id,
                'tool_name': event.tool_name,
                'tool_args': None,
                'result': event.content,
            })

    async def _persist_supervisor(self, event: NormalizedEvent) -> None:
        if isinstance(event, TokenEvent):
            return

        if isinstance(event, AITextEvent):
            text = (event.content or '').rstrip()
            if not text:
                return
            await AgentMessageService.add_assistant_message(self._message_vo(text))
            return

        if isinstance(event, ToolCallEvent):
            if self._should_hide_tool_event(event):
                return
            if event.tool_call_id:
                await AgentMessageService.save_tool_call(
                    session_id=self._ctx.session_id,
                    tool_call_id=event.tool_call_id,
                    tool_name=event.tool_name,
                    tool_args=event.tool_args,
                    user_id=self._ctx.user_id,
                    dept_id=self._ctx.dept_id,
                    create_by=self._ctx.user_name,
                )
            return

        if isinstance(event, ToolResultEvent):
            if self._should_hide_tool_event(event):
                return
            await AgentMessageService.complete_tool_call(
                session_id=self._ctx.session_id,
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                result=event.content,
                user_id=self._ctx.user_id,
                dept_id=self._ctx.dept_id,
                create_by=self._ctx.user_name,
            )
            return

        if isinstance(event, SystemMessageEvent) and event.content:
            await AgentMessageService.add_system_message(self._message_vo(event.content))
            return

        if isinstance(event, HumanMessageEvent) and event.content:
            await AgentMessageService.add_user_message(
                self._message_vo(mask_sensitive_text(event.content))
            )

    def _sse(self, event: NormalizedEvent) -> list[str]:
        if event.source == SOURCE_SUBAGENT:
            return self._sse_subagent(event)
        return self._sse_supervisor(event)

    def _sse_subagent(self, event: NormalizedEvent) -> list[str]:
        if not event.agent_ns:
            return []

        if isinstance(event, TokenEvent):
            return [format_sse(AgentSseEvent.TOKEN.value, self._tag({'content': event.content}, event.source, event.agent_ns))]

        if isinstance(event, ToolCallEvent):
            return [format_sse(AgentSseEvent.TOOL_CALL.value, self._tag({
                'tool_call_id': event.tool_call_id,
                'phase': AgentToolCallPhase.CALL.value,
                'tool_name': event.tool_name,
                'tool_args': event.tool_args,
            }, event.source, event.agent_ns))]

        if isinstance(event, ToolResultEvent):
            return [format_sse(AgentSseEvent.TOOL_CALL.value, self._tag({
                'tool_call_id': event.tool_call_id,
                'phase': AgentToolCallPhase.RESULT.value,
                'tool_name': event.tool_name,
                'content': self._parse_tool_result(event.content),
            }, event.source, event.agent_ns))]

        return []

    def _sse_supervisor(self, event: NormalizedEvent) -> list[str]:
        if isinstance(event, TokenEvent):
            return [format_sse(AgentSseEvent.TOKEN.value, self._tag({'content': event.content}, event.source, event.agent_ns))]

        if isinstance(event, ToolCallEvent):
            if self._should_hide_tool_event(event):
                return []
            return [format_sse(AgentSseEvent.TOOL_CALL.value, self._tag({
                'tool_call_id': event.tool_call_id,
                'phase': AgentToolCallPhase.CALL.value,
                'tool_name': event.tool_name,
                'tool_args': event.tool_args,
            }, event.source, event.agent_ns))]

        if isinstance(event, ToolResultEvent):
            if self._should_hide_tool_event(event):
                return []
            return [format_sse(AgentSseEvent.TOOL_CALL.value, self._tag({
                'tool_call_id': event.tool_call_id,
                'phase': AgentToolCallPhase.RESULT.value,
                'tool_name': event.tool_name,
                'content': self._parse_tool_result(event.content),
            }, event.source, event.agent_ns))]

        return []

    def _parse_tool_result(self, content: str | None) -> Any:
        content = content or ''
        try:
            parsed = json.loads(content) if content else None
            return parsed if isinstance(parsed, (dict, list)) else content
        except (json.JSONDecodeError, TypeError):
            return content

    async def _flush_subgraph_on_ns_change(self, event: NormalizedEvent) -> None:
        current_ns = event.agent_ns if event.source == SOURCE_SUBAGENT else None
        for ns in list(self._subgraph_messages.keys()):
            if ns != current_ns:
                await self._flush_subgraph(ns)

    async def _flush_all_subgraphs(self) -> None:
        for ns in list(self._subgraph_messages.keys()):
            await self._flush_subgraph(ns)

    async def _flush_subgraph(self, agent_ns: str | None) -> None:
        if not agent_ns:
            return
        messages = self._subgraph_messages.pop(agent_ns, [])
        if not messages:
            return
        remark = self._subagent_remark(agent_ns)
        for item in messages:
            if item.get('role') == 'ai':
                content = item.get('content') or ''
                if content.strip():
                    await AgentMessageService.add_assistant_message(
                        self._message_vo(content, remark=remark)
                    )
                continue
            if item.get('role') != 'tool' or not item.get('tool_call_id'):
                continue
            await AgentMessageService.save_tool_call(
                session_id=self._ctx.session_id,
                tool_call_id=item['tool_call_id'],
                tool_name=item['tool_name'],
                tool_args=item.get('tool_args') or {},
                user_id=self._ctx.user_id,
                dept_id=self._ctx.dept_id,
                create_by=self._ctx.user_name,
                remark=remark,
            )
            if item.get('result') is not None:
                await AgentMessageService.complete_tool_call(
                    session_id=self._ctx.session_id,
                    tool_call_id=item['tool_call_id'],
                    tool_name=item['tool_name'],
                    result=item['result'],
                    user_id=self._ctx.user_id,
                    dept_id=self._ctx.dept_id,
                    create_by=self._ctx.user_name,
                    remark=remark,
                )

    def _subagent_remark(self, agent_ns: str) -> str:
        return json.dumps({'source': SOURCE_SUBAGENT, 'agent_ns': agent_ns}, ensure_ascii=False)

    def _should_hide_tool_event(self, event: ToolCallEvent | ToolResultEvent) -> bool:
        return (
            event.source == SOURCE_SUPERVISOR
            and event.tool_name in self._hidden_supervisor_tools
        )

    def _tag(self, data: dict, source: str, agent_ns: str | None) -> dict:
        tagged = {**data, 'source': source}
        if agent_ns:
            tagged['agent_ns'] = agent_ns
        return tagged

    def _message_vo(self, content: str, remark: str | None = None) -> AgentMessageVo:
        return AgentMessageVo(
            session_id=self._ctx.session_id,
            content=content,
            user_id=self._ctx.user_id,
            dept_id=self._ctx.dept_id,
            create_by=self._ctx.user_name,
            remark=remark,
        )
