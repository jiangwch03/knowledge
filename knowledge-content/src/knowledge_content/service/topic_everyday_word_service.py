"""日常词：库是准的，Redis 给抽词用。人剔除后立刻刷新缓存。"""

from __future__ import annotations

import asyncio
from datetime import datetime

from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.redis import DistributedLock, LockKey, RedisClient, RedisKey
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_content.mapper.dao.topic_everyday_word_dao import TopicEverydayWordDao
from knowledge_content.mapper.do.retrieve_topic_do import KnowledgeTopicEverydayWord
from knowledge_content.service.topic_keyword_extractor import (
    SOURCE_MANUAL,
    builtin_everyday_seed,
    classify_everyday_word,
    everyday_word_source,
)
from knowledge_content.vo.topic_everyday_word_vo import (
    TopicEverydayWordAddRequest,
    TopicEverydayWordQuery,
    TopicEverydayWordRemoveRequest,
    TopicEverydayWordVo,
)

_SEED_BATCH = 500
_CACHE_LOCK = LockKey.custom_key('everyday:word:cache')
_WORD_MAX_LEN = 64


def _builtin_rows(update_by: str) -> list[KnowledgeTopicEverydayWord]:
    all_words, kept = builtin_everyday_seed()
    now = datetime.now()
    rows: list[KnowledgeTopicEverydayWord] = []
    for word in sorted(all_words):
        text = word.strip()
        if not text or len(text) > _WORD_MAX_LEN:
            continue
        removed = text in kept or text.casefold() in kept
        kind = classify_everyday_word(text)
        rows.append(
            KnowledgeTopicEverydayWord(
                word=text,
                lang=kind.lang,
                word_class=kind.word_class,
                source=everyday_word_source(text),
                create_by=update_by,
                create_time=now,
                update_by=update_by,
                update_time=now,
                del_flag=DeleteFlag.DELETED.value if removed else DeleteFlag.NORMAL.value,
            )
        )
    return rows


def _normalize_word(word: str) -> str:
    text = word.strip()
    if not text:
        raise ServiceException('请填写日常词')
    if any(ch.isspace() for ch in text):
        raise ServiceException('一次只加一个词')
    if text.isascii():
        text = text.casefold()
    if len(text) > _WORD_MAX_LEN:
        raise ServiceException('日常词最长 64 个字')
    return text


class TopicEverydayWordService:
    @classmethod
    async def list_words(cls, query: TopicEverydayWordQuery) -> PageModel:
        if await TopicEverydayWordDao.count_rows() == 0:
            await cls.refresh_cache()
        page = await TopicEverydayWordDao.list_words(
            query.word, query.lang, query.word_class, query.source, query.page_num, query.page_size,
        )
        page.rows = [TopicEverydayWordVo.model_validate(row) for row in page.rows]
        return page

    @classmethod
    async def add_word(cls, request: TopicEverydayWordAddRequest, current_user: CurrentUserModel) -> TopicEverydayWordVo:
        text = _normalize_word(request.word)
        kind = classify_everyday_word(text)
        saved = await cls._save_word(text, kind.lang, kind.word_class, current_user.user.user_name or '')
        await cls.refresh_cache()
        return saved

    @classmethod
    async def initialize_words(cls, current_user: CurrentUserModel) -> int:
        """清空日常词表，再按程序里的词表重新入库，并刷新缓存。"""
        async with DistributedLock(_CACHE_LOCK, expire=180, timeout=10) as acquired:
            if not acquired:
                raise ServiceException('日常词正在初始化，请稍后再试')
            rows = await asyncio.to_thread(_builtin_rows, current_user.user.user_name or '')
            total = await cls._replace_seed(rows)
            words = await TopicEverydayWordDao.list_active_words()
            await RedisClient.set(RedisKey.everyday_word_key(), words)
            logger.info('日常词已重新初始化，入库 {} 条，缓存 {} 条', total, len(words))
            return total

    @classmethod
    async def remove_words(cls, request: TopicEverydayWordRemoveRequest, current_user: CurrentUserModel) -> int:
        removed = await cls._mark_removed(request.word_ids, current_user.user.user_name or '')
        await cls.refresh_cache()
        return removed

    @classmethod
    async def load_for_extract(cls) -> frozenset[str]:
        """抽词用。缓存没有就从库装进 Redis。"""
        try:
            cached = await RedisClient.get(RedisKey.everyday_word_key())
        except Exception as exc:
            logger.warning('读取日常词缓存失败，改从库加载: {}', exc)
            cached = None
        if isinstance(cached, list):
            return frozenset(str(word) for word in cached if word)
        words = await cls.refresh_cache()
        return frozenset(words)

    @classmethod
    async def refresh_cache(cls) -> list[str]:
        """从库重写 Redis。表是空的就先写入内置日常词。"""
        async with DistributedLock(_CACHE_LOCK, expire=120, timeout=10) as acquired:
            if not acquired:
                return await TopicEverydayWordDao.list_active_words()
            await cls.seed_if_empty()
            words = await TopicEverydayWordDao.list_active_words()
            await RedisClient.set(RedisKey.everyday_word_key(), words)
            logger.info('日常词缓存已更新，{} 条', len(words))
            return words

    @classmethod
    async def seed_if_empty(cls) -> int:
        if await TopicEverydayWordDao.count_rows() > 0:
            return 0
        rows = await asyncio.to_thread(_builtin_rows, 'system')
        return await cls._insert_if_empty(rows)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _replace_seed(cls, rows: list[KnowledgeTopicEverydayWord]) -> int:
        await TopicEverydayWordDao.delete_all()
        return await cls._insert_rows(rows)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _insert_if_empty(cls, rows: list[KnowledgeTopicEverydayWord]) -> int:
        if await TopicEverydayWordDao.count_rows() > 0:
            return 0
        return await cls._insert_rows(rows)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _insert_rows(cls, rows: list[KnowledgeTopicEverydayWord]) -> int:
        for start in range(0, len(rows), _SEED_BATCH):
            await TopicEverydayWordDao.add_many(rows[start:start + _SEED_BATCH])
        logger.info('日常词已写入库，{} 条，其中剔除 {} 条', len(rows), sum(1 for row in rows if row.del_flag == '2'))
        return len(rows)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _save_word(cls, word: str, lang: str, word_class: str, update_by: str) -> TopicEverydayWordVo:
        now = datetime.now()
        existing = await TopicEverydayWordDao.find_by_word(word)
        if existing is not None and existing.del_flag == DeleteFlag.NORMAL.value:
            raise ServiceException('这个词已经在日常词里')
        if existing is not None:
            await TopicEverydayWordDao.restore(existing.word_id, lang, word_class, update_by, now)
            word_id = int(existing.word_id)
            source = existing.source or SOURCE_MANUAL
        else:
            source = SOURCE_MANUAL
            row = KnowledgeTopicEverydayWord(
                word=word,
                lang=lang,
                word_class=word_class,
                source=source,
                create_by=update_by,
                create_time=now,
                update_by=update_by,
                update_time=now,
                del_flag=DeleteFlag.NORMAL.value,
            )
            await TopicEverydayWordDao.add_many([row])
            word_id = int(row.word_id)
        return TopicEverydayWordVo(
            word_id=word_id,
            word=word,
            lang=lang,
            word_class=word_class,
            source=source,
            update_time=now,
        )

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _mark_removed(cls, word_ids: list[int], update_by: str) -> int:
        removed = await TopicEverydayWordDao.soft_delete(word_ids, update_by, datetime.now())
        if removed <= 0:
            raise ServiceException('没有可剔除的日常词')
        return removed
