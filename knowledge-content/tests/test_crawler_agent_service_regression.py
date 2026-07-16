"""
Agent 运行时回归测试 — interrupt 检测与 resume 构建。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from knowledge_content.agents.service.crawler_agent_service import _CrawlerAgentService


class _AsyncOnlyStateCompiled:
    """模拟 AsyncRedisSaver：同步 get_state 在主线程直接炸。"""

    def __init__(self, interrupt_value: dict | None):
        self._interrupt_value = interrupt_value
        self.aget_state_calls = 0

    def get_state(self, _config):
        raise asyncio.InvalidStateError(
            'Synchronous calls to AsyncRedisSaver are only allowed from a different thread.'
        )

    async def aget_state(self, _config):
        self.aget_state_calls += 1
        if self._interrupt_value is None:
            return SimpleNamespace(tasks=[])
        interrupt = SimpleNamespace(value=self._interrupt_value)
        task = SimpleNamespace(interrupts=[interrupt], ns=('supervisor',))
        return SimpleNamespace(tasks=[task])


@pytest.mark.asyncio
async def test_check_post_interrupt_uses_aget_state_only():
    compiled = _AsyncOnlyStateCompiled({
        'action_requests': [{'name': 'crawl_execute', 'args': {}, 'description': '确认'}],
        'review_configs': [],
    })

    events = []
    async for event in _CrawlerAgentService._check_post_interrupt(
        compiled, {'configurable': {'thread_id': '1'}},
    ):
        events.append(event)

    assert compiled.aget_state_calls == 1
    assert len(events) == 1
    assert 'event: user_choice' in events[0]
    assert 'crawl_execute' in events[0]


@pytest.mark.asyncio
async def test_build_resume_command_uses_aget_state_only():
    compiled = _AsyncOnlyStateCompiled({
        'action_requests': [{'name': 'crawl_execute', 'args': {}}],
        'review_configs': [],
    })

    cmd = await _CrawlerAgentService._build_resume_command(compiled, {}, 'approve')
    assert compiled.aget_state_calls == 1
    assert cmd.resume == {'decisions': [{'type': 'approve'}]}
