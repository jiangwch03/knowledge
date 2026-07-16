"""Supervisor / HITL resume 构建测试"""

import pytest

from knowledge_content.agents.service.crawler_agent_service import _CrawlerAgentService


class _FakeCompiled:
    def __init__(self, pending):
        self._pending = pending

    def get_state(self, _config):
        if not self._pending:
            return None

        class Task:
            interrupts = [type('I', (), {'value': self._pending})()]

        class State:
            tasks = [Task()]

        return State()

    async def aget_state(self, config):
        return self.get_state(config)


@pytest.mark.asyncio
async def test_build_resume_command_hitl():
    compiled = _FakeCompiled({
        'action_requests': [{'name': 'crawl_execute', 'args': {}}],
        'review_configs': [],
    })
    cmd = await _CrawlerAgentService._build_resume_command(compiled, {}, 'approve')
    assert cmd.resume == {'decisions': [{'type': 'approve'}]}


@pytest.mark.asyncio
async def test_build_resume_command_hitl_reject_forbids_retry():
    """用户点取消时，reject message 须明确禁止 LLM 立刻重提同一工具。"""
    compiled = _FakeCompiled({
        'action_requests': [{'name': 'crawl_execute', 'args': {}}],
        'review_configs': [],
    })
    cmd = await _CrawlerAgentService._build_resume_command(compiled, {}, 'reject')
    decisions = cmd.resume['decisions']
    assert len(decisions) == 1
    assert decisions[0]['type'] == 'reject'
    msg = decisions[0]['message']
    assert '明确拒绝' in msg or '取消' in msg
    assert '禁止' in msg and '重试' in msg


@pytest.mark.asyncio
async def test_build_resume_command_custom():
    compiled = _FakeCompiled({'type': 'strategy_confirmation', 'prompt': {'input_mode': 'choice'}})
    cmd = await _CrawlerAgentService._build_resume_command(compiled, {}, 'no')
    assert cmd.resume == 'no'
