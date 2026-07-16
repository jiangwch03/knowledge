"""preview_scope_removal 工具与服务测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_content.agents.utils.filter_chain_util import extract_filter_chain
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


def test_extract_filter_chain_from_crawl_config():
    config = {
        'crawler_run_config': {
            'deep_crawl_strategy': {
                'filter_chain': {
                    'include_patterns': ['https://example.com/docs/*'],
                    'exclude_patterns': [],
                },
            },
        },
    }
    fc = extract_filter_chain(config)
    assert fc is not None
    assert fc['include_patterns'] == ['https://example.com/docs/*']


@pytest.mark.asyncio
async def test_preview_scope_removal_computes_urls():
    crawl_config = {
        'crawler_run_config': {
            'deep_crawl_strategy': {
                'filter_chain': {
                    'include_patterns': ['https://example.com/docs/*'],
                    'exclude_patterns': [],
                },
            },
        },
    }
    mock_records = [
        MagicMock(url='https://example.com/docs/a', title='A', status='SUCCESS'),
        MagicMock(url='https://example.com/blog/b', title='B', status='SUCCESS'),
    ]

    with (
        patch.object(
            WebCrawlerTaskService,
            'get_task_with_data_scope',
            new=AsyncMock(return_value=MagicMock(task_id=42)),
        ),
        patch(
            'knowledge_content.service.web_crawler_task_service.WebCrawlerTaskUrlRecordDao.get_all_records_by_task_id',
            new=AsyncMock(return_value=mock_records),
        ),
    ):
        result = await WebCrawlerTaskService.preview_scope_removal(42, crawl_config)

    assert result['success'] is True
    assert result['removed_count'] == 1
    assert result['urls_to_remove'] == ['https://example.com/blog/b']
    assert result['crawled_success_count'] == 2


@pytest.mark.asyncio
async def test_preview_scope_removal_no_filter_chain_returns_empty():
    with patch.object(
        WebCrawlerTaskService,
        'get_task_with_data_scope',
        new=AsyncMock(return_value=MagicMock(task_id=1)),
    ):
        result = await WebCrawlerTaskService.preview_scope_removal(1, {'crawler_run_config': {}})

    assert result['success'] is True
    assert result['removed_count'] == 0
    assert result['urls_to_remove'] == []
    assert result['pages_to_remove'] == []
