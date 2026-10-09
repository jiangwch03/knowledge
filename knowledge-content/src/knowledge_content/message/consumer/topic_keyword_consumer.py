"""主题关键词抽取消息消费者。"""

from __future__ import annotations

from typing import Any

from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger

from knowledge_content.service.retrieve_topic_service import RetrieveTopicService
from knowledge_content.service.vo.message_stream_topic_vo import TopicKeywordPending


@consumer(topic=StreamTopicConfig.topic_keyword_pending, group_id=StreamTopicConfig.group_id, pre_ack=True)
async def handle_topic_keyword_pending(msg: Message) -> None:
    value: Any = msg.value or {}
    payload = TopicKeywordPending.model_validate(value)
    topic_id = payload.topic_id
    lock_key = LockKey.custom_key(f'topic:keyword:{topic_id}')
    async with DistributedLock(lock_key, expire=180, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info('[TopicKeyword] 正在抽词，跳过: topic_id={}', topic_id)
            return
        logger.info('[TopicKeyword] 开始抽词: topic_id={}', topic_id)
        try:
            await RetrieveTopicService.generate_keywords(topic_id, keep_keywords=payload.keep_keywords)
            logger.info('[TopicKeyword] 抽词结束: topic_id={}', topic_id)
        except Exception as exc:
            err = format_exception_message(exc)
            logger.exception('[TopicKeyword] 抽词失败: topic_id={}, error={}', topic_id, err)
