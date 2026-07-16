"""
pause_crawl_task 爬取任务暂停工具

暂停正在执行的后台爬取任务。
供 LLM 在用户要求暂停爬取时调用。
"""

import asyncio
import json

from langchain_core.tools import tool

from knowledge_common.common import with_session
from knowledge_common.common.context import RedisContext
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.redis.key import RedisKey
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService

# 暂停轮询超时时间（秒），与 Redis 暂停标志 TTL 对齐
_PAUSE_POLL_TTL = 600
# 轮询间隔（秒）
_PAUSE_POLL_INTERVAL = 1


@tool
@with_session
async def pause_crawl_task(task_id: int | None = None) -> str:
    """
    暂停指定的爬取任务。

    当用户要求暂停某一正在执行的爬取任务时使用此工具。
    只允许暂停 RUNNING 状态的任务。

    Args:
        task_id: 任务 ID（必填）
    """
    if task_id is None:
        logger.error('[PauseTask] 缺少 task_id')
        return json.dumps({
            'success': False,
            'task_id': None,
            'summary': '缺少任务 ID，请传入 task_id',
        }, ensure_ascii=False)

    try:
        return await _pause_crawl_task(task_id)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[PauseTask] 暂停异常: task_id={}, error={}', task_id, err)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'summary': f'暂停任务失败: {err}',
        }, ensure_ascii=False)


async def _pause_crawl_task(task_id: int) -> str:
    """
    执行暂停操作：通过 Service 校验并设置暂停标志 → 轮询等待执行器响应

    校验与设标志委托给 WebCrawlerTaskService.pause_task，
    轮询逻辑保留在工具层，用于 LLM 获取确定性结果。

    :param task_id: 爬取任务 ID
    :return: JSON 格式结果
    """
    logger.info('[PauseTask] 开始暂停任务: task_id={}', task_id)

    # 1. 通过 Service 校验任务状态并设置 Redis 暂停标志
    await WebCrawlerTaskService.pause_task(task_id)

    # 2. 轮询等待执行器响应
    redis = RedisContext.get_redis()
    pause_key = RedisKey.crawl_task_pause_key(task_id)
    poll_count = 0
    max_polls = _PAUSE_POLL_TTL // _PAUSE_POLL_INTERVAL

    while poll_count < max_polls:
        await asyncio.sleep(_PAUSE_POLL_INTERVAL)
        poll_count += 1

        if await redis.exists(pause_key):
            continue

        task = await WebCrawlerTaskService.get_task(task_id)
        # 如果任务状态为 PAUSED，则返回成功
        if task.status == CrawlTaskStatus.PAUSED.value:
            logger.info('[PauseTask] 暂停成功: task_id={}', task_id)
            return json.dumps({
                'success': True,
                'task_id': task_id,
                'status': CrawlTaskStatus.PAUSED.value,
                'progress': task.progress,
                'success_count': task.success_count,
                'failed_count': task.failed_count,
                'total_count': task.total_count,
                'summary': f'任务已暂停，当前进度: {task.progress}%',
            }, ensure_ascii=False)
        # 如果任务状态不是为 PAUSED，则返回失败
        logger.warning(
            '[PauseTask] 暂停响应异常: task_id={}, 标志已清除但状态为{}',
            task_id, task.status,
        )
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'current_status': task.status,
            'summary': f'暂停响应异常：标志已清除但任务状态为 {task.status}，请稍后查询任务详情确认',
        }, ensure_ascii=False)

    # 3. 轮询超时，执行器未响应
    logger.warning('[PauseTask] 暂停超时: task_id={}, 执行器未在{}秒内响应', task_id, _PAUSE_POLL_TTL)
    return json.dumps({
        'success': False,
        'task_id': task_id,
        'summary': f'暂停超时：执行器未在 {_PAUSE_POLL_TTL} 秒内响应，任务可能仍在继续执行',
    }, ensure_ascii=False)
