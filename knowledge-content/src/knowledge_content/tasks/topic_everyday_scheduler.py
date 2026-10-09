"""每天固定时间把库里的日常词重新装进 Redis。"""

from __future__ import annotations

from knowledge_content.service.topic_everyday_word_service import TopicEverydayWordService


async def topic_everyday_cache_job() -> None:
    """定时任务入口：03:00 从库刷新日常词缓存。"""
    await TopicEverydayWordService.refresh_cache()
