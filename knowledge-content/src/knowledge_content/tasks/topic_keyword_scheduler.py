"""
主题抽词定时兜底

GENERATING 超过 3 分钟仍未结束：抢不到执行锁说明消费者还在跑，跳过；
抢到锁说明消息丢失或进程已退出，按保存时的保留选项重新投递。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from knowledge_common.message_stream import MessageStreamService
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger

from knowledge_content.mapper.dao.retrieve_topic_dao import RetrieveTopicDao
from knowledge_content.mapper.do.retrieve_topic_do import KnowledgeRetrieveTopic
from knowledge_content.service.vo.message_stream_topic_vo import TopicKeywordPending

_STALE_MINUTES = 3


class TopicKeywordScheduler:
    @classmethod
    async def run_fallback(cls) -> None:
        before = datetime.now() - timedelta(minutes=_STALE_MINUTES)
        topics: list[KnowledgeRetrieveTopic] = await RetrieveTopicDao.list_stale_generating(before)
        if not topics:
            return
        logger.info('[TopicKeyword-scheduler] 扫描到 {} 个超时生成中主题', len(topics))
        for topic in topics:
            topic_id = int(topic.topic_id)
            keep_keywords = topic.keep_keywords == '1'
            lock_key = LockKey.custom_key(f'topic:keyword:{topic_id}')
            try:
                async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
                    if not acquired:
                        continue
                await MessageStreamService.produce(
                    topic=StreamTopicConfig.topic_keyword_pending,
                    value=TopicKeywordPending(topic_id=topic_id, keep_keywords=keep_keywords),
                    key=str(topic_id),
                )
                logger.info('[TopicKeyword-scheduler] 重投递: topic_id={}', topic_id)
            except Exception as exc:
                logger.exception('[TopicKeyword-scheduler] 重投递失败: topic_id={}, error={}', topic_id, exc)


async def topic_keyword_fallback_job() -> None:
    """定时任务入口：生成中超时则重投抽词消息。"""
    await TopicKeywordScheduler.run_fallback()
