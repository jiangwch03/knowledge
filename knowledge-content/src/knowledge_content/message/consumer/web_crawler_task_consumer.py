"""
knowledge-content 爬取任务消息消费者

- crawl.task.pending: 消费爬取任务并执行
"""
from __future__ import annotations

from knowledge_common.common.transactional import with_session
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger
from knowledge_content.service.web_crawler_task_executor_service import WebCrawlerTaskExecutorService


# pre_ack=True: 框架在调用 handler 前先 ACK 消息,移出 PEL
# 避免 claim_idle_loop 因爬取耗时数分钟而每 5s 空转一次
# 任务执行失败由 retry_failed_tasks 定时任务扫描 DB FAILED 状态兜底
# @with_session 须在 @consumer 内侧：consumer 只注册 handler，实际调用的是 with_session 包装后的函数
@consumer(topic=StreamTopicConfig.crawl_task_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
@with_session
async def handle_crawl_task_pending(msg: Message) -> None:
    """
    爬取任务消费者：接收消息并执行爬取任务

    消息 payload 格式：{"task_id": 123}

    注意:此消费者标记了 pre_ack=True,消息会在 handler 执行前被框架 ACK。
    因此 handler 内无需(也不应)关注任何 ACK 操作。若任务执行失败,
    由 retry_failed_tasks 定时任务扫描 DB 中 FAILED 状态后重新投递。

    :param msg: 消息对象
    """
    value = msg.value or {}
    task_id = value.get('task_id')
    if not task_id:
        logger.warning('[CrawlConsumer] 消息缺少 task_id，跳过')
        return

    async with DistributedLock(LockKey.crawl_task_key(task_id), renew=True) as acquired:
        if not acquired:
            logger.warning(f'[CrawlConsumer] 爬取任务正在被其他消费者处理，跳过: task_id={task_id}')
            return

        await WebCrawlerTaskExecutorService.execute_task(task_id)
