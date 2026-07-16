"""
knowledge-content 爬取文档合并消费者

- crawl.document.pending: 将已爬取成功的页面合并落库为知识库文档
"""
from __future__ import annotations

from knowledge_common.common.transactional import with_session
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.web_crawler_task_dao import WebCrawlerTaskDao
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import WebCrawlerTaskUrlRecordDao
from knowledge_content.service.crawler_document_service import CrawlerDocumentService
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo
from knowledge_content.service.vo.message_stream_topic_vo import CrawlDocumentPending
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


# pre_ack=True: 框架在调用 handler 前先 ACK 消息,移出 PEL
# 避免 claim_idle_loop 因 Markdown 合并(几百页可能耗时数分钟)而空转
# persist_documents 内部已 try-catch,异常时设 CONVERT_FAILED 并 return(不抛异常),
# 失败兜底由 retry_failed_tasks 定时任务扫描 CONVERT_FAILED 重新发布 crawl.document.pending
@consumer(topic=StreamTopicConfig.crawl_document_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
@with_session
async def handle_crawl_document_pending(msg: Message) -> None:
    """
    爬取文档合并消费者：消费后标 CONVERTING，再合并落库。

    消息 payload 格式：{"task_id": 123, "target_url": "https://..."}

    注意:此消费者标记了 pre_ack=True,消息会在 handler 执行前被框架 ACK。
    若合并失败,由 retry_failed_tasks 扫描 CONVERT_FAILED 后重新投递本 topic。

    :param msg: 消息对象
    """
    value = msg.value or {}
    payload = CrawlDocumentPending.model_validate(value)
    task_id = payload.task_id
    target_url = payload.target_url

    # 分布式锁(renew=True)：与爬取执行、删除等操作共用的同一把任务级锁
    lock_key = LockKey.crawl_task_key(task_id)
    async with DistributedLock(lock_key, expire=300, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info(f'[CrawlDocConsumer] 文档合并正在处理中，跳过: task_id={task_id}')
            return

        task = await WebCrawlerTaskDao.get_task_by_id(task_id)
        if not task:
            logger.warning(f'[CrawlDocConsumer] 任务不存在，跳过: task_id={task_id}')
            return

        if task.status not in (
            CrawlTaskStatus.COMPLETED.value,
            CrawlTaskStatus.CONVERT_FAILED.value,
            CrawlTaskStatus.CONVERTING.value,
        ):
            logger.info(
                f'[CrawlDocConsumer] 任务状态不可合并，跳过: task_id={task_id}, status={task.status}'
            )
            return

        exist_doc = await KnowledgeDocumentDao.get_document_by_task_id(
            task_id, DocumentSourceType.CRAWL.value,
        )
        if exist_doc:
            logger.info(
                f'[CrawlDocConsumer] 文档已存在，跳过: task_id={task_id}, doc_id={exist_doc.doc_id}'
            )
            return

        # 消费到位后立即标转换中，再跑合并（与「发消息后不管」对应：界面能看到合并中）
        if task.status != CrawlTaskStatus.CONVERTING.value:
            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.CONVERTING.value,
            )
            logger.info(f'[CrawlDocConsumer] 已标记转换中: task_id={task_id}')

        # 从 URL 记录表重建成功结果（执行阶段已将每页 markdown 上传 MinIO 并写入 doc_key）
        success_records = await WebCrawlerTaskUrlRecordDao.get_success_records_with_doc_key(task_id)
        results = [
            CrawlProcessedVo(
                success=True,
                url=record.url,
                title=record.title or '',
                object_name=record.doc_key,
            )
            for record in success_records
        ]

        logger.info(
            f'[CrawlDocConsumer] 开始合并文档: task_id={task_id}, url={target_url}, pages={len(results)}'
        )
        await CrawlerDocumentService.persist_documents(task_id, target_url, results)
        logger.info(f'[CrawlDocConsumer] 文档合并处理完成: task_id={task_id}, pages={len(results)}')
