"""直连 deepagents 模式下的流式事件映射测试。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langgraph.types import Overwrite

from knowledge_common.agent.runtime.stream_processor import AgentStreamProcessor
from knowledge_common.agent.schema.context import AgentIdentityContextVo
from knowledge_common.agent.stream import normalize_astream


class _FakeCompiled:
    def __init__(self, items):
        self._items = items

    async def astream(self, *_args, **_kwargs) -> AsyncIterator:
        for item in self._items:
            yield item


@pytest.mark.asyncio
async def test_normalize_astream_accepts_empty_namespaces_in_direct_mode(monkeypatch):
    """顶层 updates 带空 namespaces；messages 可为 Overwrite（deepagents 真实形态）。"""
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.stream_processor.AgentMessageService.add_assistant_message',
        AsyncMock(),
    )

    fake_compiled = _FakeCompiled([
        {'ns': (), 'type': 'messages', 'data': (AIMessageChunk(content='A'), {})},
        {'ns': (), 'type': 'updates', 'data': {
            'supervisor': {
                'messages': Overwrite(value=[AIMessage(content='summary')]),
            },
        }},
    ])

    context = AgentIdentityContextVo(
        session_id=1, user_id=1, dept_id=1, user_name='tester', model_id=None,
    )
    events: list[str] = []
    async for event in AgentStreamProcessor(context).run(
        fake_compiled,
        {'configurable': {'thread_id': 't1'}},
        {'messages': []},
    ):
        events.append(event)

    assert any('event: token' in e and '"content": "A"' in e for e in events)

    # 验证 normalize_astream 本身也能消费同类数据
    normalized = []
    async for item in normalize_astream(
        fake_compiled,
        config={'configurable': {'thread_id': 't1'}},
        context=context.model_dump(),
        input_or_resume={'messages': []},
    ):
        normalized.append(item)
    assert normalized
