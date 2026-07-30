"""
knowledge-content 爬取任务定时任务

- 超时兜底：扫描 RUNNING 超过阈值的任务，写 Redis 取消标志，由活执行器自报 FAILED+TIMEOUT
- 僵尸收尸：扫描 update_time 停更超过宽限的 RUNNING 任务
  - 执行锁仍被占用：仍在跑（如大页后处理），跳过
  - 执行锁可抢到：进程已死 → 直接 PENDING 续跑（不计 retry_count）
- PENDING 消息重投：扫描卡住的 PENDING 任务，重发 crawl.task.pending（兜底 produce 失败/pre_ack 后丢失）
- COMPLETED 消息重投：扫描爬取完成但未进入落库链路的任务，重发 crawl.document.pending
- 失败重试：扫描 FAILED 状态且重试次数未达上限的任务，触发自动重试
- 文档合并重试：扫描 CONVERT_FAILED 状态的任务，重发 crawl.document.pending 触发合并消费者
"""
from __future__ import annotations

from datetime import datetime, timedelta

from knowledge_common.common.context import RedisContext
from knowledge_common.config.env import Crawl4aiConfig, StreamTopicConfig
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.redis import DistributedLock, LockKey, RedisKey
from knowledge_common.utils.log_util import logger

from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.dao.web_crawler_task_dao import WebCrawlerTaskDao
from knowledge_content.service.vo.message_stream_topic_vo import CrawlDocumentPending, CrawlTaskPending
from knowledge_content.service.web_crawler_task_retry_service import WebCrawlerTaskRetryService
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService

# 创建/完成后至少等待这么久才重投，避免与刚发出的正常消息赛跑
_PENDING_REQUEUE_GRACE_MINUTES = 2
_COMPLETED_REQUEUE_GRACE_MINUTES = 2


class WebCrawlerTaskScheduler:
    """
    爬取任务定时任务调度器
    """

    @classmethod
    async def timeout_fallback(cls) -> None:
        """
        先处理真实超时，再处理僵尸 RUNNING（两套逻辑隔离）
        """
        await cls._handle_overtime_running_tasks()
        await cls._handle_zombie_running_tasks()

    @classmethod
    async def _handle_overtime_running_tasks(cls) -> None:
        """
        真实超时兜底：started_time 超过阈值的 RUNNING 任务

        只写 Redis 取消标志，通知（可能）仍在跑的执行器自报 FAILED+TIMEOUT。
        若进程已死无人读标志，由 _handle_zombie_running_tasks 凭执行锁直接续跑。
        """
        timeout_minutes = Crawl4aiConfig.crawl4ai_task_timeout_minutes
        timeout_before = datetime.now() - timedelta(minutes=timeout_minutes)
        tasks = await WebCrawlerTaskDao.get_tasks_by_status_and_time_before(
            status=CrawlTaskStatus.RUNNING.value,
            time_before=timeout_before,
        )
        logger.info(
            f'[CrawlScheduler] 超时扫描: 命中 {len(tasks)} 个 RUNNING 任务'
            f'（阈值={timeout_minutes}分钟）'
        )

        for task in tasks:
            task_id = task.task_id
            try:
                # 超时只负责通知活执行器停跑；进程是否已死由后续僵尸扫描用锁判定
                await cls._set_cancel_flag(task_id)
                logger.info(f'[CrawlScheduler] 任务超时，已发取消通知: task_id={task_id}')
            except Exception as e:
                logger.exception('[CrawlScheduler] 超时处理失败: task_id={}, error={}', task_id, e)

    @classmethod
    async def _handle_zombie_running_tasks(cls) -> None:
        """
        僵尸 RUNNING 收尸：update_time 停更超过宽限

        - 抢不到执行锁：执行器仍在跑（例如单页后处理较慢）→ 跳过
        - 抢到执行锁：进程已死 → 直接 PENDING 续跑（不计 retry_count）
        """
        zombie_minutes = Crawl4aiConfig.crawl4ai_zombie_detect_minutes
        update_before = datetime.now() - timedelta(minutes=zombie_minutes)
        tasks = await WebCrawlerTaskDao.get_zombie_running_tasks(update_before)
        logger.info(
            f'[CrawlScheduler] 僵尸扫描: 命中 {len(tasks)} 个 RUNNING 任务'
            f'（停更宽限={zombie_minutes}分钟）'
        )

        for task in tasks:
            task_id = task.task_id
            try:
                async with DistributedLock(
                    LockKey.crawl_task_key(task_id),
                    expire=30,
                    timeout=0,
                ) as acquired:
                    if not acquired:
                        logger.debug(
                            f'[CrawlScheduler] 停更但仍持有执行锁，跳过: task_id={task_id}'
                        )
                        continue

                    # 持锁仅改状态；消息放到锁外，避免执行器抢锁失败
                    await WebCrawlerTaskService.mark_pending_after_process_died(task_id)

                await MessageStreamService.produce(
                    topic=StreamTopicConfig.crawl_task_pending,
                    value=CrawlTaskPending(task_id=task_id),
                    key=str(task_id),
                )
                logger.info(f'[CrawlScheduler] 僵尸 RUNNING 已续跑: task_id={task_id}')
            except Exception as e:
                logger.exception('[CrawlScheduler] 僵尸收尸失败: task_id={}, error={}', task_id, e)

    @classmethod
    async def _set_cancel_flag(cls, task_id: int) -> None:
        """
        设置任务取消标志

        在 Redis 中设置取消标志 key，TTL 为 10 分钟。
        爬取循环中会检查此标志，发现后主动抛出异常停止执行。

        :param task_id: 任务ID
        """
        redis = RedisContext.get_redis()
        cancel_key = RedisKey.crawl_task_cancel_key(task_id)
        # 设置标志，TTL 10 分钟（足够爬取协程检测到并停止）
        await redis.set(cancel_key, '1', ex=600)
        logger.info(f'[CrawlScheduler] 设置取消标志: task_id={task_id}')

    @classmethod
    async def _requeue_stale_pending_tasks(cls) -> None:
        """
        PENDING 消息重投兜底：扫出创建超过宽限期仍停留在 PENDING 的任务，重发执行消息。

        覆盖场景：
        - create_task 落库成功但 produce 失败
        - pre_ack 后拿锁失败 / handler 异常，消息已 ACK 且任务未进入 RUNNING
        """
        cutoff = datetime.now() - timedelta(minutes=_PENDING_REQUEUE_GRACE_MINUTES)
        pending_tasks = await WebCrawlerTaskDao.get_pending_tasks_created_before(cutoff)
        logger.info(
            f'[CrawlScheduler] PENDING 重投: 扫描到 {len(pending_tasks)} 个超时未执行任务'
            f'（宽限={_PENDING_REQUEUE_GRACE_MINUTES}分钟）'
        )

        for task in pending_tasks:
            try:
                await MessageStreamService.produce(
                    topic=StreamTopicConfig.crawl_task_pending,
                    value=CrawlTaskPending(task_id=task.task_id),
                    key=str(task.task_id),
                )
                logger.info(f'[CrawlScheduler] PENDING 重投消息已发送: task_id={task.task_id}')
            except Exception as e:
                logger.exception('[CrawlScheduler] PENDING 重投失败: task_id={}, error={}', task.task_id, e)

    @classmethod
    async def _requeue_stale_completed_tasks(cls) -> None:
        """
        COMPLETED 消息重投兜底：扫出完成超过宽限期仍停留在 COMPLETED 的任务，重发落库消息。

        覆盖场景：
        - complete_task 落库成功但 produce crawl.document.pending 失败
        - pre_ack 后消费者拿锁失败 / handler 异常，消息已 ACK 且任务未进入 CONVERTING
        """
        cutoff = datetime.now() - timedelta(minutes=_COMPLETED_REQUEUE_GRACE_MINUTES)
        completed_tasks = await WebCrawlerTaskDao.get_completed_tasks_before(cutoff)
        logger.info(
            f'[CrawlScheduler] COMPLETED 重投: 扫描到 {len(completed_tasks)} 个超时未落库任务'
            f'（宽限={_COMPLETED_REQUEUE_GRACE_MINUTES}分钟）'
        )

        for task in completed_tasks:
            try:
                await MessageStreamService.produce(
                    topic=StreamTopicConfig.crawl_document_pending,
                    value=CrawlDocumentPending(task_id=task.task_id, target_url=task.target_url),
                    key=str(task.task_id),
                )
                logger.info(f'[CrawlScheduler] COMPLETED 重投消息已发送: task_id={task.task_id}')
            except Exception as e:
                logger.exception('[CrawlScheduler] COMPLETED 重投失败: task_id={}, error={}', task.task_id, e)

    @classmethod
    async def retry_failed_tasks(cls) -> None:
        """
        失败重试入口：依次处理 PENDING / COMPLETED / CONVERT_FAILED / FAILED 四类兜底。

        分布式锁：job 级互斥，防止上一次重试批次尚未执行完毕时下一次定时触发重复执行。
        新的定时触发若未抢到锁则直接跳过，等下一轮再来。
        """
        async with DistributedLock(
            LockKey.crawl_task_retry_job_key(),
            expire=300,
            timeout=0,
            renew=True,
        ) as acquired:
            if not acquired:
                logger.info('[CrawlScheduler] 失败重试: 上一次重试仍在执行中，跳过本次触发')
                return
            await cls._requeue_stale_pending_tasks()
            await cls._requeue_stale_completed_tasks()
            await cls._retry_convert_failed_tasks()
            await cls._auto_retry_failed_tasks()

    @classmethod
    async def _retry_convert_failed_tasks(cls) -> None:
        """
        文档合并重试：扫描 CONVERT_FAILED 任务，重发 crawl.document.pending。

        仅触发合并消费者，不改任务状态、不递增 retry_count。
        """
        convert_failed_tasks = await WebCrawlerTaskDao.get_tasks_by_status(
            status=CrawlTaskStatus.CONVERT_FAILED.value,
        )
        logger.info(
            f'[CrawlScheduler] 文档合并重试: 扫描到 {len(convert_failed_tasks)} 个 CONVERT_FAILED 任务'
        )

        for task in convert_failed_tasks:
            try:
                await MessageStreamService.produce(
                    topic=StreamTopicConfig.crawl_document_pending,
                    value=CrawlDocumentPending(task_id=task.task_id, target_url=task.target_url),
                    key=str(task.task_id),
                )
                logger.info(f'[CrawlScheduler] 文档合并重试消息已发送: task_id={task.task_id}')
            except Exception as e:
                logger.exception('[CrawlScheduler] 文档合并重试失败: task_id={}, error={}', task.task_id, e)

    @classmethod
    async def _auto_retry_failed_tasks(cls) -> None:
        """
        爬取失败自动重试：扫描 FAILED 任务，通过 WebCrawlerTaskRetryService 尝试修复并重试。
        """
        failed_tasks = await WebCrawlerTaskDao.get_tasks_by_status(
            status=CrawlTaskStatus.FAILED.value,
        )
        logger.info(f'[CrawlScheduler] 失败重试: 扫描到 {len(failed_tasks)} 个失败任务')

        for task in failed_tasks:
            try:
                retried = await WebCrawlerTaskRetryService.try_auto_retry(task.task_id)
                if retried:
                    logger.info(f'[CrawlScheduler] 自动重试成功: task_id={task.task_id}')
                else:
                    logger.info(
                        f'[CrawlScheduler] 自动重试失败或已标记最终状态: task_id={task.task_id}'
                    )
            except Exception as e:
                logger.exception('[CrawlScheduler] 重试处理异常: task_id={}, error={}', task.task_id, e)

# APScheduler 可调用的顶层异步函数


async def crawl_task_timeout_job() -> None:
    """爬取任务超时兜底定时任务入口"""
    await WebCrawlerTaskScheduler.timeout_fallback()


async def crawl_task_retry_job() -> None:
    """爬取任务失败重试定时任务入口"""
    await WebCrawlerTaskScheduler.retry_failed_tasks()
