"""直连 deepagents 模式下 resume_stream 行为测试。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.types import Command

from knowledge_content.agents.service.crawler_agent_service import _CrawlerAgentService


class _FakeCompiled:
    def __init__(self, interrupt_value: dict | None):
        self._interrupt_value = interrupt_value

    def get_state(self, _config):
        if self._interrupt_value is None:
            return SimpleNamespace(tasks=[])
        interrupt = SimpleNamespace(value=self._interrupt_value)
        task = SimpleNamespace(interrupts=[interrupt], ns=("supervisor",))
        return SimpleNamespace(tasks=[task])

    async def aget_state(self, config):
        return self.get_state(config)


@pytest.mark.asyncio
async def test_resume_stream_hitl_approve_maps_to_approve(monkeypatch):
    fake_compiled = _FakeCompiled(
        {
            "action_requests": [{"name": "crawl_execute", "args": {}}],
            "review_configs": [],
        }
    )

    monkeypatch.setattr(_CrawlerAgentService, "get_graph", AsyncMock(return_value=fake_compiled))
    monkeypatch.setattr(
        'knowledge_common.agent.runtime.chat_service.AgentSessionService.get_session_vo',
        AsyncMock(return_value=SimpleNamespace(model_id=321)),
    )

    seen_resume: dict = {}

    async def _fake_run(self, compiled, config, input_or_resume):
        assert compiled is fake_compiled
        assert config == {"configurable": {"thread_id": "77"}}
        assert isinstance(input_or_resume, Command)
        seen_resume["value"] = input_or_resume.resume
        yield 'event: token\ndata: {"content":"ok"}\n\n'

    monkeypatch.setattr(
        'knowledge_common.agent.runtime.chat_service.AgentStreamProcessor.run',
        _fake_run,
    )

    events = []
    async for event in _CrawlerAgentService.resume_stream(
        session_id=77,
        resume_value='approve',
        user_id=1001,
        dept_id=2001,
        create_by='tester',
    ):
        events.append(event)

    assert seen_resume["value"] == {"decisions": [{"type": "approve"}]}
    assert any("event: token" in e for e in events)


@pytest.mark.asyncio
async def test_resume_stream_without_pending_interrupt_returns_error(monkeypatch):
    fake_compiled = _FakeCompiled(interrupt_value=None)
    monkeypatch.setattr(_CrawlerAgentService, "get_graph", AsyncMock(return_value=fake_compiled))

    async def _should_not_run(self, *_args, **_kwargs):
        raise AssertionError("AgentStreamProcessor.run should not be called without pending interrupt")
        if False:
            yield ""

    monkeypatch.setattr(
        'knowledge_common.agent.runtime.chat_service.AgentStreamProcessor.run',
        _should_not_run,
    )

    events = []
    async for event in _CrawlerAgentService.resume_stream(
        session_id=88,
        resume_value='yes',
        user_id=1001,
        dept_id=2001,
        create_by='tester',
    ):
        events.append(event)

    assert len(events) == 1
    assert "event: error" in events[0]
    assert "无 pending interrupt" in events[0]
