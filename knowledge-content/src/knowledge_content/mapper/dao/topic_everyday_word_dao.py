from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.dao.base_dao import BaseDao
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.mapper.do.retrieve_topic_do import KnowledgeTopicEverydayWord


class TopicEverydayWordDao(BaseDao):
    @staticmethod
    async def count_rows() -> int:
        db: AsyncSession = get_current_session()
        total = (
            await db.execute(select(func.count()).select_from(KnowledgeTopicEverydayWord))
        ).scalar()
        return int(total or 0)

    @staticmethod
    async def find_by_word(word: str) -> KnowledgeTopicEverydayWord | None:
        db: AsyncSession = get_current_session()
        return (
            await db.execute(
                select(KnowledgeTopicEverydayWord).where(KnowledgeTopicEverydayWord.word == word)
            )
        ).scalar_one_or_none()

    @staticmethod
    async def delete_all() -> int:
        db: AsyncSession = get_current_session()
        result = await db.execute(delete(KnowledgeTopicEverydayWord))
        return int(result.rowcount or 0)

    async def add_many(rows: list[KnowledgeTopicEverydayWord]) -> None:
        db: AsyncSession = get_current_session()
        db.add_all(rows)
        await db.flush()

    @staticmethod
    async def list_active_words() -> list[str]:
        db: AsyncSession = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeTopicEverydayWord.word).where(
                    KnowledgeTopicEverydayWord.del_flag == DeleteFlag.NORMAL.value,
                )
            )
        ).scalars()
        return [word for word in rows if word]

    @staticmethod
    async def list_words(
        word: str | None,
        lang: str | None,
        word_class: str | None,
        source: str | None,
        page_num: int,
        page_size: int,
    ) -> PageModel:
        query = (
            select(
                KnowledgeTopicEverydayWord.word_id,
                KnowledgeTopicEverydayWord.word,
                KnowledgeTopicEverydayWord.lang,
                KnowledgeTopicEverydayWord.word_class,
                KnowledgeTopicEverydayWord.source,
                KnowledgeTopicEverydayWord.update_time,
            )
            .where(KnowledgeTopicEverydayWord.del_flag == DeleteFlag.NORMAL.value)
            .order_by(KnowledgeTopicEverydayWord.word_id.asc())
        )
        text = (word or '').strip()
        if text:
            query = query.where(KnowledgeTopicEverydayWord.word.like(f'%{text}%'))
        language = (lang or '').strip()
        if language:
            query = query.where(KnowledgeTopicEverydayWord.lang == language)
        kind = (word_class or '').strip()
        if kind:
            query = query.where(KnowledgeTopicEverydayWord.word_class == kind)
        origin = (source or '').strip()
        if origin:
            query = query.where(KnowledgeTopicEverydayWord.source == origin)
        return await PageUtil.paginate(query, page_num, page_size, is_page=True)

    @staticmethod
    async def restore(word_id: int, lang: str, word_class: str, update_by: str, now: datetime) -> None:
        db: AsyncSession = get_current_session()
        await db.execute(
            update(KnowledgeTopicEverydayWord)
            .where(KnowledgeTopicEverydayWord.word_id == word_id)
            .values(
                lang=lang,
                word_class=word_class,
                del_flag=DeleteFlag.NORMAL.value,
                update_by=update_by,
                update_time=now,
            )
        )

    @staticmethod
    async def soft_delete(word_ids: list[int], update_by: str, now: datetime) -> int:
        db: AsyncSession = get_current_session()
        result = await db.execute(
            update(KnowledgeTopicEverydayWord)
            .where(
                KnowledgeTopicEverydayWord.word_id.in_(word_ids),
                KnowledgeTopicEverydayWord.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=now)
        )
        return int(result.rowcount or 0)
