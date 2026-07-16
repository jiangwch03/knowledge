"""失败重试：进程中断不计次；上限取任务 max_retry_count"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.service.web_crawler_task_retry_service import WebCrawlerTaskRetryService


@pytest.mark.asyncio
async def test_process_died_requeues_without_counting_retry():
    task = MagicMock()
    task.error_code = CrawlTaskErrorCode.PROCESS_DIED.value
    task.retry_count = 2
    task.max_retry_count = 2

    with (
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.get_task',
            new=AsyncMock(return_value=task),
        ),
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.requeue_after_process_died',
            new_callable=AsyncMock,
        ) as requeue,
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.retry_task',
            new_callable=AsyncMock,
        ) as retry_task,
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.update_task_status',
            new_callable=AsyncMock,
        ) as update_status,
    ):
        ok = await WebCrawlerTaskRetryService.try_auto_retry(15)

    assert ok is True
    requeue.assert_awaited_once_with(15)
    retry_task.assert_not_awaited()
    update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_uses_task_max_retry_count_before_user_decision():
    task = MagicMock()
    task.error_code = CrawlTaskErrorCode.TIMEOUT.value
    task.retry_count = 3
    task.max_retry_count = 4

    with (
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.get_task',
            new=AsyncMock(return_value=task),
        ),
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.retry_task',
            new_callable=AsyncMock,
        ) as retry_task,
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.update_task_status',
            new_callable=AsyncMock,
        ) as update_status,
    ):
        ok = await WebCrawlerTaskRetryService.try_auto_retry(15)

    assert ok is True
    retry_task.assert_awaited_once_with(15)
    update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_reaches_task_max_retry_count_upgrades_user_decision():
    task = MagicMock()
    task.error_code = CrawlTaskErrorCode.TIMEOUT.value
    task.retry_count = 4
    task.max_retry_count = 4

    with (
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.get_task',
            new=AsyncMock(return_value=task),
        ),
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.retry_task',
            new_callable=AsyncMock,
        ) as retry_task,
        patch(
            'knowledge_content.service.web_crawler_task_retry_service.WebCrawlerTaskService.update_task_status',
            new_callable=AsyncMock,
        ) as update_status,
    ):
        ok = await WebCrawlerTaskRetryService.try_auto_retry(15)

    assert ok is False
    retry_task.assert_not_awaited()
    update_status.assert_awaited_once_with(15, CrawlTaskStatus.USER_DECISION.value)
