"""
knowledge-content 爬取文档落库消费者

- crawl.document.pending: 将已爬取成功的页面写入知识库文档主表 + 文件子表
"""
from __future__ import annotations

from knowledge_common.common.transactional import with_session
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger
from knowledge_content.service.crawler_document_service import CrawlerDocumentService
from knowledge_content.service.vo.message_stream_topic_vo import CrawlDocumentPending


# pre_ack=True: 框架在调用 handler 前先 ACK 消息,移出 PEL
# persist_documents 内部已 try-catch,异常时设 CONVERT_FAILED 并 return(不抛异常),
# 失败兜底由 retry_failed_tasks 定时任务扫描 COMPLETED / CONVERT_FAILED 重新发布 crawl.document.pending
@consumer(topic=StreamTopicConfig.crawl_document_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
@with_session
async def handle_crawl_document_pending(msg: Message) -> None:
    """
    爬取文档落库消费者：消费后标 CONVERTING，再写主表+文件子表。

    消息 payload 格式：{"task_id": 123, "target_url": "https://..."}
    """
    value = msg.value or {}
    payload = CrawlDocumentPending.model_validate(value)
    task_id = payload.task_id

    lock_key = LockKey.crawl_task_key(task_id)
    async with DistributedLock(lock_key, expire=300, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info(f'[CrawlDocConsumer] 文档落库正在处理中，跳过: task_id={task_id}')
            return
        logger.info(
            f'[CrawlDocConsumer] 开始落库文档: task_id={task_id}'
        )
        await CrawlerDocumentService.persist_documents(task_id)
        logger.info(f'[CrawlDocConsumer] 文档落库处理完成: task_id={task_id}')
