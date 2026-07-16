"""子图 updates 缓冲与 flush 落库回归。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from knowledge_common.agent.runtime.stream_processor import AgentStreamProcessor
from knowledge_common.agent.schema.context import AgentIdentityContextVo
from knowledge_common.agent.stream import (
    SOURCE_SUBAGENT,
    SOURCE_SUPERVISOR,
    AITextEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)


def _processor() -> AgentStreamProcessor:
    return AgentStreamProcessor(
        AgentIdentityContextVo(session_id=1, user_id=1001, dept_id=2001, user_name='tester', model_id=None)
    )


@pytest.mark.asyncio
async def test_subgraph_token_does_not_buffer():
    processor = _processor()
    ns = 'planning|model'
    await processor._persist(TokenEvent(source=SOURCE_SUBAGENT, agent_ns=ns, content='分析中'))
    assert processor._subgraph_messages == {}


@pytest.mark.asyncio
async def test_subgraph_tool_buffered_until_flush(monkeypatch):
    save_tool_call = AsyncMock()
    complete_tool_call = AsyncMock()
    add_assistant_message = AsyncMock()
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.save_tool_call',
        save_tool_call,
    )
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.complete_tool_call',
        complete_tool_call,
    )
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.add_assistant_message',
        add_assistant_message,
    )

    processor = _processor()
    ns = 'planning|model'

    await processor._persist(ToolCallEvent(
        source=SOURCE_SUBAGENT,
        agent_ns=ns,
        tool_call_id='call_1',
        tool_name='fetch_page',
        tool_args={'url': 'https://example.com'},
    ))
    await processor._persist(ToolResultEvent(
        source=SOURCE_SUBAGENT,
        agent_ns=ns,
        tool_call_id='call_1',
        tool_name='fetch_page',
        content='{"ok": true}',
    ))

    save_tool_call.assert_not_awaited()
    complete_tool_call.assert_not_awaited()

    await processor._flush_subgraph(ns)

    save_tool_call.assert_awaited_once()
    complete_tool_call.assert_awaited_once()
    add_assistant_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_subgraph_flush_persists_updates_in_order(monkeypatch):
    save_tool_call = AsyncMock()
    complete_tool_call = AsyncMock()
    add_assistant_message = AsyncMock()
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.save_tool_call',
        save_tool_call,
    )
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.complete_tool_call',
        complete_tool_call,
    )
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.add_assistant_message',
        add_assistant_message,
    )

    processor = _processor()
    ns = 'planning|model'

    await processor._persist(AITextEvent(source=SOURCE_SUBAGENT, agent_ns=ns, content='分析中'))
    await processor._persist(ToolCallEvent(
        source=SOURCE_SUBAGENT,
        agent_ns=ns,
        tool_call_id='call_1',
        tool_name='fetch_page',
        tool_args={'url': 'https://example.com'},
    ))
    await processor._persist(ToolResultEvent(
        source=SOURCE_SUBAGENT,
        agent_ns=ns,
        tool_call_id='call_1',
        tool_name='fetch_page',
        content='done',
    ))

    save_tool_call.assert_not_awaited()
    complete_tool_call.assert_not_awaited()

    await processor._flush_subgraph(ns)

    add_assistant_message.assert_awaited_once()
    save_tool_call.assert_awaited_once()
    complete_tool_call.assert_awaited_once()
    remark = add_assistant_message.await_args.args[0].remark
    assert '"source": "subagent"' in remark
    assert ns in remark


@pytest.mark.asyncio
async def test_subgraph_ns_change_flushes_tools_even_without_text(monkeypatch):
    flush_subgraph = AsyncMock()
    processor = _processor()
    monkeypatch.setattr(processor, '_flush_subgraph', flush_subgraph)

    ns = 'planning|model'
    await processor._persist(ToolCallEvent(
        source=SOURCE_SUBAGENT,
        agent_ns=ns,
        tool_call_id='call_1',
        tool_name='fetch_page',
        tool_args={'url': 'https://example.com'},
    ))

    await processor._flush_subgraph_on_ns_change(TokenEvent(source=SOURCE_SUPERVISOR, agent_ns=None, content='x'))

    flush_subgraph.assert_awaited_once_with(ns)


@pytest.mark.asyncio
async def test_supervisor_tool_still_persists_immediately(monkeypatch):
    save_tool_call = AsyncMock()
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.save_tool_call',
        save_tool_call,
    )

    processor = _processor()
    await processor._persist(ToolCallEvent(
        source=SOURCE_SUPERVISOR,
        agent_ns=None,
        tool_call_id='call_parent',
        tool_name='query_crawl_task',
        tool_args={'task_id': 1},
    ))

    save_tool_call.assert_awaited_once()
    assert processor._subgraph_messages == {}
