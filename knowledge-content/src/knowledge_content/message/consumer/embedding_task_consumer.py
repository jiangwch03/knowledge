"""
knowledge-content Embedding 任务消息消费者

- embedding.pending: 切分 + 向量化流水线
"""
from __future__ import annotations

from typing import Any

from knowledge_common.common.transactional import with_session
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger

from knowledge_content.service.embedding_task_service import EmbeddingTaskService
from knowledge_content.service.vo.message_stream_topic_vo import EmbeddingPending


@consumer(topic=StreamTopicConfig.embedding_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
@with_session
async def handle_embedding_pending(msg: Message) -> None:
    value: Any = msg.value or {}
    payload: EmbeddingPending = EmbeddingPending.model_validate(value)
    task_id: int = payload.task_id

    lock_key: str = LockKey.embedding_task_key(task_id)
    async with DistributedLock(lock_key, expire=180, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info('[Embedding-consumer] 任务正在处理中，跳过: task_id={}', task_id)
            return

        logger.info('[Embedding-consumer] 开始处理: task_id={}', task_id)
        try:
            await EmbeddingTaskService.process_pending(task_id)
            logger.info('[Embedding-consumer] 处理结束: task_id={}', task_id)
        except Exception as exc:
            err: str = format_exception_message(exc)
            logger.exception('[Embedding-consumer] 处理失败: task_id={}, error={}', task_id, err)
        
