"""deepagents 架构单元测试（HITL resume / apply_scope_change）"""

from types import SimpleNamespace

import pytest

from knowledge_content.agents.service.crawler_agent_service import _CrawlerAgentService
from knowledge_content.agents.tools.apply_scope_change import _normalize_urls_to_remove


class _FakeCompiled:
    def __init__(self, pending):
        self._pending = pending

    def get_state(self, _config):
        if not self._pending:
            return None

        class Interrupt:
            def __init__(self, value):
                self.value = value

        class Task:
            def __init__(self, value):
                self.interrupts = [Interrupt(value)]

        class State:
            def __init__(self, value):
                self.tasks = [Task(value)]

        return State(self._pending)

    async def aget_state(self, config):
        return self.get_state(config)


@pytest.mark.asyncio
async def test_build_resume_command_non_hitl_passthrough():
    compiled = _FakeCompiled({'type': 'legacy', 'prompt': {}})
    cmd = await _CrawlerAgentService._build_resume_command(compiled, {}, 'yes')
    assert cmd.resume == 'yes'


def test_hitl_user_choice_event_has_choice_mode():
    event = _CrawlerAgentService.format_hitl_user_choice_event({
        'action_requests': [{'name': 'crawl_execute', 'args': {}, 'description': '确认提交'}],
        'review_configs': [],
    })
    assert event is not None
    assert '"input_mode": "choice"' in event
    assert 'crawl_execute' in event


def test_apply_scope_change_normalize_urls_to_remove():
    urls = _normalize_urls_to_remove([
        'https://example.com/blog/1',
        '',
        'https://example.com/blog/1',
        'https://example.com/blog/2',
    ])
    assert urls == [
        'https://example.com/blog/1',
        'https://example.com/blog/2',
    ]
