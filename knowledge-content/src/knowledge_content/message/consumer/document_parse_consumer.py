"""
knowledge-content Stage2 / Stage4 消息消费者

- document.parse.pending: 申请 MinerU 上传链接并上传分段
- document.md.pending: 合并 Markdown 并入库
"""
from __future__ import annotations

from knowledge_common.common.transactional import async_session_scope
from knowledge_common.config.env import StreamTopicConfig
from knowledge_content.enums.document_upload_status_enum import DocumentUploadStatus
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger

from knowledge_content.enums.mineru_parse_task_status_enum import MineruParseTaskStatus
from knowledge_content.mapper.dao.mineru_parse_task_dao import KnowledgeMineruParseTaskDao
from knowledge_content.mapper.dao.upload_task_dao import KnowledgeUploadTaskDao
from knowledge_content.service.document_upload_parse_service import DocumentUploadParseService
from knowledge_content.service.vo.message_stream_topic_vo import DocumentMdPending, DocumentParsePending


# pre_ack=True: 框架在调用 handler 前先 ACK 消息,移出 PEL
# 避免 claim_idle_loop 因解析+上传耗时数分钟而空转
# 失败兜底:Stage2-A 定时任务每分钟扫描 LINK_FAILED + PENDING 重试
@consumer(topic=StreamTopicConfig.document_parse_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
async def handle_document_parse_pending(msg: Message) -> None:
    """
    Stage2 消费者：处理解析任务

    注意:此消费者标记了 pre_ack=True,消息会在 handler 执行前被框架 ACK。
    因此 handler 内无需(也不应)关注任何 ACK 操作。若任务执行失败,
    由 Stage2-A 定时任务扫描 LINK_FAILED/PENDING 状态后重新处理。

    :param msg: 消息对象
    """
    value = msg.value or {}
    payload = DocumentParsePending.model_validate(value)
    parse_task_id = payload.parse_task_id
    
    # 先查询任务获取 task_id
    task = await KnowledgeMineruParseTaskDao.get_task_by_id(parse_task_id)
    if not task:
        logger.info(f'[Stage2-consumer] 解析任务不存在，跳过: parse_task_id={parse_task_id}')
        return
    
    # 分布式锁(renew=True)：基于 task_id，与删除接口互斥；看门狗自动续期防止锁过期
    lock_key = LockKey.upload_task_key(task.task_id)
    async with DistributedLock(lock_key, expire=120, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info(f'[Stage2-consumer] 上传任务正在处理中，跳过: parse_task_id={parse_task_id}, task_id={task.task_id}')
            return
        
        logger.info(f'[Stage2-consumer] 开始处理解析任务: parse_task_id={parse_task_id}')
        try:
            await DocumentUploadParseService.process_pending_task(parse_task_id)
        except Exception as e:
            err = format_exception_message(e)
            logger.exception(
                '[Stage2-consumer] 解析任务处理失败: parse_task_id={}, error={}',
                parse_task_id, err,
            )
            async with async_session_scope() as session:
                await KnowledgeMineruParseTaskDao.update_status(
                    parse_task_id,
                    MineruParseTaskStatus.LINK_FAILED.value,
                    error_code='STAGE2_ERROR',
                    error_message=err,
                )
                await KnowledgeUploadTaskDao.update_status(
                    task.task_id,
                    DocumentUploadStatus.LINK_FAILED.value,
                    error_code='STAGE2_ERROR',
                    error_message=err,
                )
                await session.commit()
        logger.info(f'[Stage2-consumer] 解析任务处理完成: parse_task_id={parse_task_id}')


# pre_ack=True:框架在调用 handler 前先 ACK 消息,移出 PEL
# 避免 claim_idle_loop 因 Markdown 合并耗时数分钟而空转
# 失败兜底:Stage4 定时任务每分钟扫描 CONVERT_FAILED 重试
@consumer(topic=StreamTopicConfig.document_md_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
async def handle_document_md_pending(msg: Message) -> None:
    """
    Stage4 消费者：合并 Markdown 并入库

    注意:此消费者标记了 pre_ack=True,消息会在 handler 执行前被框架 ACK。
    若 task_id 对应的上传记录为 CONVERT_FAILED,由 Stage4 定时任务兜底重试。

    :param msg: 消息对象
    """
    value = msg.value or {}
    payload = DocumentMdPending.model_validate(value)
    task_id = payload.task_id
    
    # 分布式锁(renew=True)：防止同时处理同一上传任务；看门狗自动续期防止锁过期
    lock_key = LockKey.upload_task_key(task_id)
    async with DistributedLock(lock_key, expire=180, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info(f'[Stage4-consumer] 上传任务正在处理中，跳过: task_id={task_id}')
            return
        
        logger.info(f'[Stage4-consumer] 开始合并 Markdown: task_id={task_id}')
        try:
            await DocumentUploadParseService.process_md_pending(task_id)
        except Exception as e:
            err = format_exception_message(e)
            logger.exception(
                '[Stage4-consumer] Markdown 合并失败: task_id={}, error={}',
                task_id, err,
            )
            async with async_session_scope() as session:
                await KnowledgeUploadTaskDao.update_status(
                    task_id,
                    DocumentUploadStatus.CONVERT_FAILED.value,
                    error_code='STAGE4_ERROR',
                    error_message=err,
                )
                await session.commit()
        logger.info(f'[Stage4-consumer] Markdown 合并完成: task_id={task_id}')
