from pydantic import BaseModel, Field
from sqlalchemy import select

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.dao.base_dao import BaseDao
from knowledge_retrieval.mapper.do.retrieve_topic_ro_do import (
    KnowledgeRetrieveTopicKeywordRo,
    KnowledgeRetrieveTopicRo,
)


class ActiveTopicBriefVo(BaseModel):
    """交给主题模型的一条主题。"""

    topic_name: str
    description: str = ''


class ActiveTopicCatalogVo(BaseModel):
    """已完成主题的名称、描述和关键词。"""

    topics: list[ActiveTopicBriefVo] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class RetrieveTopicRoDao(BaseDao):
    @staticmethod
    async def list_active_catalog() -> ActiveTopicCatalogVo:
        db = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeRetrieveTopicRo.topic_name, KnowledgeRetrieveTopicRo.description)
                .where(
                    KnowledgeRetrieveTopicRo.del_flag == DeleteFlag.NORMAL.value,
                    KnowledgeRetrieveTopicRo.status == 'READY',
                )
                .order_by(KnowledgeRetrieveTopicRo.topic_id.asc())
            )
        ).all()
        keywords = (
            (
                await db.execute(
                    select(KnowledgeRetrieveTopicKeywordRo.keyword)
                    .join(
                        KnowledgeRetrieveTopicRo,
                        KnowledgeRetrieveTopicRo.topic_id == KnowledgeRetrieveTopicKeywordRo.topic_id,
                    )
                    .where(
                        KnowledgeRetrieveTopicRo.del_flag == DeleteFlag.NORMAL.value,
                        KnowledgeRetrieveTopicRo.status == 'READY',
                        KnowledgeRetrieveTopicKeywordRo.del_flag == DeleteFlag.NORMAL.value,
                    )
                )
            )
            .scalars()
            .all()
        )
        return ActiveTopicCatalogVo(
            topics=[
                ActiveTopicBriefVo(topic_name=name, description=(description or '').strip())
                for name, description in rows
                if name
            ],
            keywords=[word for word in keywords if word],
        )
