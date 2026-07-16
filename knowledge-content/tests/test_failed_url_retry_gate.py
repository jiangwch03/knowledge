"""失败样本 URL 解析与 crawl_retry 试爬门禁。"""

import json
from unittest.mock import AsyncMock

import pytest

from knowledge_content.agents.utils.failed_url_samples import (
    parse_failed_urls_from_error_message,
)
from knowledge_content.agents.utils import crawl_submit_gate as gate


def test_parse_failed_urls_from_error_message():
    msg = (
        '全部 2 个URL爬取失败: https://milvus.io/docs/zh/milvus-webui.md [EMPTY_CONTENT] 页面正文为空; '
        'https://milvus.io/docs/zh/quickstart.md [EMPTY_CONTENT] 页面正文为空'
    )
    assert parse_failed_urls_from_error_message(msg) == [
        'https://milvus.io/docs/zh/milvus-webui.md',
        'https://milvus.io/docs/zh/quickstart.md',
    ]


@pytest.mark.asyncio
async def test_prepare_crawl_submit_rejects_when_no_failed_url_verified(monkeypatch):
    class _Identity:
        session_id = 16
        user_id = 1
        dept_id = None
        user_name = 'admin'

    monkeypatch.setattr(
        gate,
        'get_agent_identity_from_tool_runtime',
        lambda _runtime: _Identity(),
    )
    monkeypatch.setattr(
        gate,
        'evaluate_seed_scope',
        lambda *_a, **_k: {
            'expansion_ok': True,
            'seed_in_scope': True,
            'suggested_seed_urls': [],
            'issues': [],
            'suggestions': [],
        },
    )
    monkeypatch.setattr(gate, 'is_any_trial_verified', AsyncMock(return_value=False))

    failed = [f'https://ex.com/doc/{i}.md' for i in range(1, 100)]
    result = await gate.prepare_crawl_submit(
        runtime=object(),
        crawl_config_arg={'crawler_run_config': {'wait_for': 'main'}},
        target_url='https://ex.com/docs/',
        require_nonempty_config=True,
        log_tag='CrawlRetry',
        action_hint='再重试',
        require_trial_urls=failed,
        also_require_target_trial=False,
    )
    assert isinstance(result, str)
    payload = json.loads(result)
    assert payload['success'] is False
    assert payload['failed_url_count'] == 99
    assert '任意一个' in payload['summary']


@pytest.mark.asyncio
async def test_prepare_crawl_submit_passes_when_99th_failed_url_verified(monkeypatch):
    """第 99 个失败页试通也应过门禁（不限前 3 候选）。"""
    class _Identity:
        session_id = 16
        user_id = 1
        dept_id = None
        user_name = 'admin'

    monkeypatch.setattr(
        gate,
        'get_agent_identity_from_tool_runtime',
        lambda _runtime: _Identity(),
    )
    monkeypatch.setattr(
        gate,
        'evaluate_seed_scope',
        lambda *_a, **_k: {
            'expansion_ok': True,
            'seed_in_scope': True,
            'suggested_seed_urls': [],
            'issues': [],
            'suggestions': [],
        },
    )
    monkeypatch.setattr(gate, 'is_any_trial_verified', AsyncMock(return_value=True))

    failed = [f'https://ex.com/doc/{i}.md' for i in range(1, 100)]
    result = await gate.prepare_crawl_submit(
        runtime=object(),
        crawl_config_arg={'crawler_run_config': {'wait_for': 'main'}},
        target_url='https://ex.com/docs/',
        require_nonempty_config=True,
        log_tag='CrawlRetry',
        action_hint='再重试',
        require_trial_urls=failed,
        also_require_target_trial=False,
    )
    assert isinstance(result, gate.CrawlSubmitPrepared)
    gate.is_any_trial_verified.assert_awaited()
    # 传入的是全部失败 URL，而非截断前 3
    assert len(gate.is_any_trial_verified.await_args.args[1]) == 99
