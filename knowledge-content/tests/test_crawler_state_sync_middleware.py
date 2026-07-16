"""CrawlerStateSyncMiddleware：query → state；Planning 终稿 → crawl_config"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from knowledge_content.agents.middleware.crawler_state_sync_middleware import (
    CrawlerStateSyncMiddleware,
    build_state_updates_from_query_payload,
    extract_urls_from_text,
)
from knowledge_content.agents.tools.crawl_task_query import query_crawl_task


def test_extract_urls_from_text_keeps_order():
    text = '失败: https://a.com/x [TIMEOUT]；另 https://a.com/x 与 https://b.com/y'
    assert extract_urls_from_text(text) == ['https://a.com/x', 'https://b.com/y']


def test_build_state_updates_from_query_payload_found_task():
    payload = {
        'success': True,
        'query_by': 'task_id',
        'task_id': 42,
        'target_url': 'https://milvus.io/docs/zh/',
        'crawl_config': {'browser_config': {'headless': True}},
        'error_message': 'https://milvus.io/docs/zh/a.md [TIMEOUT] N/A',
        'accessible': True,
    }
    updates = build_state_updates_from_query_payload(payload)
    assert updates['task_id'] == 42
    assert updates['target_url'] == 'https://milvus.io/docs/zh/'
    assert updates['crawl_config']['browser_config']['headless'] is True
    assert updates['failed_reason'].startswith('https://milvus.io')
    assert updates['failed_urls'] == ['https://milvus.io/docs/zh/a.md']


def test_build_state_updates_prefers_failed_url_details():
    payload = {
        'success': True,
        'query_by': 'task_id',
        'task_id': 15,
        'target_url': 'https://milvus.io/docs/zh/',
        'error_message': '全部 2 个URL爬取失败: https://milvus.io/docs/zh/milvus-webui.md [EMPTY_CONTENT] 页面正文为空',
        'failed_url_details': [
            {
                'url': 'https://milvus.io/docs/zh/milvus-webui.md',
                'error_code': 'EMPTY_CONTENT',
                'error_message': (
                    '页面正文为空（content_length=1, html_length=8200, status_code=200）；'
                    'HTML有内容但Markdown几乎为空，优先检查 css_selector'
                ),
                'status_code': 200,
                'title': None,
            },
            {
                'url': 'https://milvus.io/docs/zh/quickstart.md',
                'error_code': 'EMPTY_CONTENT',
                'error_message': '页面正文为空（content_length=0, html_length=100）',
                'status_code': 200,
                'title': None,
            },
        ],
        'accessible': True,
    }
    updates = build_state_updates_from_query_payload(payload)
    assert updates['failed_urls'] == [
        'https://milvus.io/docs/zh/milvus-webui.md',
        'https://milvus.io/docs/zh/quickstart.md',
    ]
    assert 'html_length=8200' in updates['failed_reason']
    assert 'css_selector' in updates['failed_reason']
    assert 'quickstart.md' in updates['failed_reason']


def test_build_state_updates_from_query_payload_not_found_keeps_url_only():
    payload = {
        'success': True,
        'query_by': 'target_url',
        'found': False,
        'target_url': 'https://example.com/docs',
        'summary': '可按新站出方案',
    }
    updates = build_state_updates_from_query_payload(payload)
    assert updates == {'target_url': 'https://example.com/docs'}


@pytest.mark.asyncio
async def test_wrap_tool_call_syncs_query_into_command():
    mw = CrawlerStateSyncMiddleware()
    payload = {
        'success': True,
        'query_by': 'task_id',
        'task_id': 7,
        'target_url': 'https://example.com',
        'crawl_config': {'crawler_run_config': {'stream': True}},
        'accessible': True,
    }
    tool_msg = ToolMessage(
        content=__import__('json').dumps(payload, ensure_ascii=False),
        tool_call_id='call-1',
        name=query_crawl_task.name,
    )
    request = MagicMock()
    request.tool_call = {'name': query_crawl_task.name, 'id': 'call-1', 'args': {}}

    async def handler(_req):
        return tool_msg

    result = await mw.awrap_tool_call(request, handler)
    assert isinstance(result, Command)
    assert result.update['task_id'] == 7
    assert result.update['crawl_config']['crawler_run_config']['stream'] is True
    assert result.update['messages'] == [tool_msg]


def test_after_agent_extracts_crawl_config_from_final_ai():
    mw = CrawlerStateSyncMiddleware()
    state = {
        'messages': [
            HumanMessage(content='分析'),
            AIMessage(content='思考中', tool_calls=[{
                'name': 'fetch_page', 'args': {}, 'id': 't1', 'type': 'tool_call',
            }]),
            ToolMessage(content='ok', tool_call_id='t1'),
            AIMessage(content=(
                '```json\n'
                '{"browser_config": {"headless": true}, '
                '"crawler_run_config": {"stream": true}, '
                '"strategy_summary": "测试"}\n'
                '```'
            )),
        ],
    }
    update = mw.after_agent(state, runtime=None)
    assert update is not None
    assert update['crawl_config']['browser_config']['headless'] is True
    assert 'strategy_summary' not in update['crawl_config']
