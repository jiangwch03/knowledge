"""crawl_submit_gate 单元测试：解析 URL / 拒绝载荷形状。"""

import json

import pytest

from knowledge_content.agents.utils.crawl_submit_gate import (
    parse_submit_crawl_config,
    resolve_effective_target_url,
)


def test_resolve_effective_target_url_prefers_explicit():
    assert resolve_effective_target_url(
        ' https://new.example/docs ',
        'https://old.example/',
    ) == 'https://new.example/docs'


def test_resolve_effective_target_url_fallback():
    assert resolve_effective_target_url(None, ' https://old.example/ ') == 'https://old.example/'
    assert resolve_effective_target_url('  ', 'https://old.example/') == 'https://old.example/'
    assert resolve_effective_target_url(None, None) == ''


def test_parse_submit_crawl_config_require_nonempty():
    err = parse_submit_crawl_config(None, log_tag='Test', require_nonempty=True)
    assert isinstance(err, str)
    payload = json.loads(err)
    assert payload['success'] is False
    assert payload['summary'] == payload['message']
    assert '缺少爬取配置' in payload['summary']


def test_parse_submit_crawl_config_allow_empty():
    parsed = parse_submit_crawl_config(None, log_tag='Test', require_nonempty=False)
    assert parsed == {}


@pytest.mark.asyncio
async def test_prepare_crawl_submit_rejects_empty_url(monkeypatch):
    from knowledge_content.agents.utils import crawl_submit_gate as gate

    class _Identity:
        session_id = 1
        user_id = 1
        dept_id = None
        user_name = 'u'

    monkeypatch.setattr(
        gate,
        'get_agent_identity_from_tool_runtime',
        lambda _runtime: _Identity(),
    )

    result = await gate.prepare_crawl_submit(
        runtime=object(),
        crawl_config_arg={'max_pages': 10},
        target_url='',
        fallback_url='',
        require_nonempty_config=True,
        log_tag='Test',
        action_hint='再提交',
    )
    assert isinstance(result, str)
    payload = json.loads(result)
    assert payload['success'] is False
    assert '目标 URL' in payload['summary']
