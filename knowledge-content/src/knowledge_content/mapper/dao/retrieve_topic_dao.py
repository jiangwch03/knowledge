from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.dao.base_dao import BaseDao
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.retrieve_topic_status_enum import RetrieveTopicStatus
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_content.mapper.do.retrieve_topic_do import KnowledgeRetrieveTopic, KnowledgeRetrieveTopicKeyword
from knowledge_content.vo.retrieve_topic_vo import TopicKeywordWeightVo, TopicSourceSegmentVo


class RetrieveTopicDao(BaseDao):
    @staticmethod
    async def get_by_id(topic_id: int) -> KnowledgeRetrieveTopic | None:
        db: AsyncSession = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeRetrieveTopic)
                    .where(
                        KnowledgeRetrieveTopic.topic_id == topic_id,
                        KnowledgeRetrieveTopic.del_flag == DeleteFlag.NORMAL.value,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def exists_name(topic_name: str) -> bool:
        db: AsyncSession = get_current_session()
        row = (
            (
                await db.execute(
                    select(KnowledgeRetrieveTopic.topic_id).where(
                        KnowledgeRetrieveTopic.topic_name == topic_name,
                        KnowledgeRetrieveTopic.del_flag == DeleteFlag.NORMAL.value,
                    )
                )
            )
            .scalars()
            .first()
        )
        return row is not None

    @staticmethod
    async def add(topic: KnowledgeRetrieveTopic) -> KnowledgeRetrieveTopic:
        db: AsyncSession = get_current_session()
        db.add(topic)
        await db.flush()
        return topic

    @staticmethod
    async def list_topics(topic_name: str | None, page_num: int, page_size: int) -> PageModel:
        query = (
            select(
                KnowledgeRetrieveTopic.topic_id,
                KnowledgeRetrieveTopic.topic_name,
                KnowledgeRetrieveTopic.description,
                KnowledgeRetrieveTopic.task_id,
                KnowledgeRetrieveTopic.doc_id,
                KnowledgeRetrieveTopic.keyword_count,
                KnowledgeRetrieveTopic.status,
                KnowledgeRetrieveTopic.error_message,
                KnowledgeRetrieveTopic.create_by,
                KnowledgeRetrieveTopic.create_time,
                KnowledgeRetrieveTopic.update_time,
                KnowledgeDocument.doc_title,
            )
            .outerjoin(
                KnowledgeDocument,
                (KnowledgeDocument.doc_id == KnowledgeRetrieveTopic.doc_id)
                & (KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value),
            )
            .where(KnowledgeRetrieveTopic.del_flag == DeleteFlag.NORMAL.value)
            .order_by(KnowledgeRetrieveTopic.topic_id.desc())
        )
        if topic_name:
            query = query.where(KnowledgeRetrieveTopic.topic_name.like(f'%{topic_name}%'))
        return await PageUtil.paginate(query, page_num, page_size, is_page=True)

    @staticmethod
    async def list_source_segments(task_id: int) -> list[TopicSourceSegmentVo]:
        """父块，以及没有父块的独立块。子块不取出。"""
        db: AsyncSession = get_current_session()
        rows = (
            await db.execute(
                select(
                    KnowledgeDocumentSegment.text,
                    KnowledgeDocumentSegment.parent_chunk_id,
                    KnowledgeDocumentSegment.skip_embedding,
                ).where(
                    KnowledgeDocumentSegment.task_id == task_id,
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,
                    or_(
                        KnowledgeDocumentSegment.skip_embedding == 1,
                        KnowledgeDocumentSegment.parent_chunk_id.is_(None),
                        KnowledgeDocumentSegment.parent_chunk_id == '',
                    ),
                )
            )
        ).all()
        return [
            TopicSourceSegmentVo(text=text, parent_chunk_id=parent_chunk_id, skip_embedding=skip_embedding)
            for text, parent_chunk_id, skip_embedding in rows
        ]

    @staticmethod
    async def list_keywords(topic_id: int) -> list[KnowledgeRetrieveTopicKeyword]:
        db: AsyncSession = get_current_session()
        return list(
            (
                await db.execute(
                    select(KnowledgeRetrieveTopicKeyword)
                    .where(
                        KnowledgeRetrieveTopicKeyword.topic_id == topic_id,
                        KnowledgeRetrieveTopicKeyword.del_flag == DeleteFlag.NORMAL.value,
                    )
                    .order_by(KnowledgeRetrieveTopicKeyword.weight.desc(), KnowledgeRetrieveTopicKeyword.keyword_id.asc())
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def replace_keywords(topic_id: int, keywords: list[TopicKeywordWeightVo], now: datetime) -> None:
        db: AsyncSession = get_current_session()
        await db.execute(
            update(KnowledgeRetrieveTopicKeyword)
            .where(
                KnowledgeRetrieveTopicKeyword.topic_id == topic_id,
                KnowledgeRetrieveTopicKeyword.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_time=now)
        )
        for item in keywords:
            db.add(
                KnowledgeRetrieveTopicKeyword(
                    topic_id=topic_id,
                    keyword=item.keyword,
                    weight=item.weight,
                    create_time=now,
                    update_time=now,
                    del_flag=DeleteFlag.NORMAL.value,
                )
            )
        await db.flush()

    @staticmethod
    async def list_stale_generating(before: datetime) -> list[KnowledgeRetrieveTopic]:
        """生成中且更新时间早于 before 的主题，供定时任务重投。"""
        db: AsyncSession = get_current_session()
        rows = await db.execute(
            select(KnowledgeRetrieveTopic).where(
                KnowledgeRetrieveTopic.del_flag == DeleteFlag.NORMAL.value,
                KnowledgeRetrieveTopic.status == RetrieveTopicStatus.GENERATING.value,
                KnowledgeRetrieveTopic.update_time < before,
            )
        )
        return list(rows.scalars().all())

    @staticmethod
    async def soft_delete(topic_id: int, update_by: str, now: datetime) -> None:
        db: AsyncSession = get_current_session()
        await db.execute(
            update(KnowledgeRetrieveTopic)
            .where(
                KnowledgeRetrieveTopic.topic_id == topic_id,
                KnowledgeRetrieveTopic.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=now)
        )
        await db.execute(
            update(KnowledgeRetrieveTopicKeyword)
            .where(
                KnowledgeRetrieveTopicKeyword.topic_id == topic_id,
                KnowledgeRetrieveTopicKeyword.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_time=now)
        )
