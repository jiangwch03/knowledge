"""超时兜底与僵尸 RUNNING 收尸：两套逻辑隔离"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_content.tasks.web_crawler_task_scheduler import WebCrawlerTaskScheduler


def _task(*, task_id: int = 13, started_delta_minutes: int = 3, update_delta_minutes: int = 3):
    now = datetime.now()
    task = MagicMock()
    task.task_id = task_id
    task.started_time = now - timedelta(minutes=started_delta_minutes)
    task.update_time = now - timedelta(minutes=update_delta_minutes)
    return task


class _LockCtx:
    def __init__(self, acquired: bool):
        self._acquired = acquired

    async def __aenter__(self):
        return self._acquired

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_overtime_only_sets_cancel_flag():
    overtime = _task(started_delta_minutes=90, update_delta_minutes=1)

    with (
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskDao.get_tasks_by_status_and_time_before',
            new=AsyncMock(return_value=[overtime]),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskDao.get_zombie_running_tasks',
            new=AsyncMock(return_value=[]),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskService.update_task_status',
            new_callable=AsyncMock,
        ) as update_status,
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskScheduler._set_cancel_flag',
            new_callable=AsyncMock,
        ) as cancel_flag,
    ):
        await WebCrawlerTaskScheduler.timeout_fallback()

    cancel_flag.assert_awaited_once_with(13)
    update_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_zombie_dead_process_requeues_without_retry():
    zombie = _task(started_delta_minutes=3, update_delta_minutes=3)

    with (
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskDao.get_tasks_by_status_and_time_before',
            new=AsyncMock(return_value=[]),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskDao.get_zombie_running_tasks',
            new=AsyncMock(return_value=[zombie]),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.DistributedLock',
            side_effect=lambda *a, **k: _LockCtx(True),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskService.mark_pending_after_process_died',
            new_callable=AsyncMock,
        ) as mark_pending,
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.MessageStreamService.produce',
            new_callable=AsyncMock,
        ) as produce,
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskScheduler._set_cancel_flag',
            new_callable=AsyncMock,
        ) as cancel_flag,
    ):
        await WebCrawlerTaskScheduler.timeout_fallback()

    mark_pending.assert_awaited_once_with(13)
    produce.assert_awaited_once()
    cancel_flag.assert_not_awaited()


@pytest.mark.asyncio
async def test_zombie_live_executor_skips():
    zombie = _task(started_delta_minutes=3, update_delta_minutes=3)

    with (
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskDao.get_tasks_by_status_and_time_before',
            new=AsyncMock(return_value=[]),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskDao.get_zombie_running_tasks',
            new=AsyncMock(return_value=[zombie]),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.DistributedLock',
            side_effect=lambda *a, **k: _LockCtx(False),
        ),
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskService.mark_pending_after_process_died',
            new_callable=AsyncMock,
        ) as mark_pending,
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.MessageStreamService.produce',
            new_callable=AsyncMock,
        ) as produce,
        patch(
            'knowledge_content.tasks.web_crawler_task_scheduler.WebCrawlerTaskScheduler._set_cancel_flag',
            new_callable=AsyncMock,
        ) as cancel_flag,
    ):
        await WebCrawlerTaskScheduler.timeout_fallback()

    mark_pending.assert_not_awaited()
    produce.assert_not_awaited()
    cancel_flag.assert_not_awaited()
