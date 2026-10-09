"""主题维护：保存后异步抽关键词。"""

from __future__ import annotations

import asyncio
from datetime import datetime

from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.enums.retrieve_topic_status_enum import RetrieveTopicStatus
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.dao.retrieve_topic_dao import RetrieveTopicDao
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.mapper.do.retrieve_topic_do import KnowledgeRetrieveTopic, KnowledgeRetrieveTopicKeyword
from knowledge_content.service.topic_everyday_word_service import TopicEverydayWordService
from knowledge_content.service.topic_keyword_extractor import (
    extract_topic_keywords,
    resolve_topic_keywords,
    select_source_texts,
)
from knowledge_content.service.vo.message_stream_topic_vo import TopicKeywordPending
from knowledge_content.vo.retrieve_topic_vo import (
    RetrieveTopicCreateRequest,
    RetrieveTopicDetailVo,
    RetrieveTopicKeywordVo,
    RetrieveTopicListItemVo,
    RetrieveTopicListQuery,
    RetrieveTopicUpdateRequest,
    TopicKeywordWeightVo,
)


class RetrieveTopicService:
    @classmethod
    async def list_topics(cls, query: RetrieveTopicListQuery) -> PageModel:
        page: PageModel = await RetrieveTopicDao.list_topics(query.topic_name, query.page_num, query.page_size)
        page.rows = [RetrieveTopicListItemVo.model_validate(row) for row in page.rows]
        return page

    @classmethod
    async def get_topic(cls, topic_id: int) -> RetrieveTopicDetailVo:
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None:
            raise ServiceException('主题不存在')
        return await cls._to_detail(topic)

    @classmethod
    async def create_topic(
        cls,
        request: RetrieveTopicCreateRequest,
        current_user: CurrentUserModel,
    ) -> RetrieveTopicDetailVo:
        saved = await cls._insert_generating(request, current_user)
        await cls._publish_generate(saved.topic_id, keep_keywords=False)
        return await cls.get_topic(saved.topic_id)

    @classmethod
    async def update_topic(
        cls,
        topic_id: int,
        request: RetrieveTopicUpdateRequest,
        current_user: CurrentUserModel,
    ) -> RetrieveTopicDetailVo:
        await cls._mark_regenerating(topic_id, request, current_user)
        await cls._publish_generate(topic_id, keep_keywords=request.keep_keywords)
        return await cls.get_topic(topic_id)

    @classmethod
    async def retry_topic(cls, topic_id: int, current_user: CurrentUserModel) -> RetrieveTopicDetailVo:
        keep_keywords = await cls._mark_retry(topic_id, current_user)
        await cls._publish_generate(topic_id, keep_keywords=keep_keywords)
        return await cls.get_topic(topic_id)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def delete_topic(cls, topic_id: int, current_user: CurrentUserModel) -> None:
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None:
            raise ServiceException('主题不存在')
        await RetrieveTopicDao.soft_delete(topic_id, current_user.user.user_name or '', datetime.now())

    @classmethod
    async def generate_keywords(cls, topic_id: int, *, keep_keywords: bool) -> None:
        """消费端抽词。只处理仍处于生成中的主题。"""
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None or topic.status != RetrieveTopicStatus.GENERATING.value:
            return
        task_id = int(topic.task_id)
        try:
            keywords = await cls._build_keywords(topic_id, task_id, keep_keywords=keep_keywords)
        except Exception as exc:
            await cls._mark_failed(topic_id, format_exception_message(exc))
            return
        if not keywords:
            await cls._mark_failed(topic_id, '没有抽出关键词')
            return
        await cls._finish(topic_id, keywords)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _insert_generating(
        cls,
        request: RetrieveTopicCreateRequest,
        current_user: CurrentUserModel,
    ) -> KnowledgeRetrieveTopic:
        if await RetrieveTopicDao.exists_name(request.topic_name):
            raise ServiceException('主题名称已存在')
        task = await cls._require_completed_task(request.task_id)
        now = datetime.now()
        operator = current_user.user.user_name or ''
        topic = KnowledgeRetrieveTopic(
            topic_name=request.topic_name,
            description=request.description,
            task_id=task.task_id,
            doc_id=task.doc_id,
            keyword_limit=0,
            keyword_count=0,
            status=RetrieveTopicStatus.GENERATING.value,
            keep_keywords='0',
            user_id=current_user.user.user_id,
            dept_id=current_user.user.dept_id,
            create_by=operator,
            create_time=now,
            update_by=operator,
            update_time=now,
        )
        return await RetrieveTopicDao.add(topic)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _mark_regenerating(
        cls,
        topic_id: int,
        request: RetrieveTopicUpdateRequest,
        current_user: CurrentUserModel,
    ) -> None:
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None:
            raise ServiceException('主题不存在')
        if topic.status == RetrieveTopicStatus.GENERATING.value:
            raise ServiceException('主题正在生成关键词')
        task = await cls._require_completed_task(request.task_id)
        now = datetime.now()
        topic.task_id = task.task_id
        topic.doc_id = task.doc_id
        topic.description = request.description
        topic.keyword_limit = 0
        topic.status = RetrieveTopicStatus.GENERATING.value
        topic.keep_keywords = '1' if request.keep_keywords else '0'
        topic.error_message = None
        topic.update_by = current_user.user.user_name or ''
        topic.update_time = now

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _mark_retry(cls, topic_id: int, current_user: CurrentUserModel) -> bool:
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None:
            raise ServiceException('主题不存在')
        if topic.status != RetrieveTopicStatus.FAILED.value:
            raise ServiceException('只有失败的主题可以重试')
        keep_keywords = topic.keep_keywords == '1'
        now = datetime.now()
        topic.status = RetrieveTopicStatus.GENERATING.value
        topic.error_message = None
        topic.update_by = current_user.user.user_name or ''
        topic.update_time = now
        return keep_keywords

    @classmethod
    async def _publish_generate(cls, topic_id: int, *, keep_keywords: bool) -> None:
        try:
            await MessageStreamService.produce(
                topic=StreamTopicConfig.topic_keyword_pending,
                value=TopicKeywordPending(topic_id=topic_id, keep_keywords=keep_keywords),
                key=str(topic_id),
            )
        except Exception as exc:
            err = format_exception_message(exc)
            logger.exception('发布主题抽词消息失败: topic_id={}, error={}', topic_id, err)
            await cls._mark_failed(topic_id, f'发布抽词消息失败: {err}')
            raise ServiceException(f'发布抽词消息失败: {err}') from exc

    @classmethod
    async def _build_keywords(
        cls,
        topic_id: int,
        task_id: int,
        *,
        keep_keywords: bool,
    ) -> list[TopicKeywordWeightVo]:
        everyday = await TopicEverydayWordService.load_for_extract()
        fresh = await cls._extract(task_id, everyday)
        existing: list[TopicKeywordWeightVo] = []
        if keep_keywords:
            rows = await RetrieveTopicDao.list_keywords(topic_id)
            existing = [TopicKeywordWeightVo(keyword=row.keyword, weight=float(row.weight or 0)) for row in rows]
        return resolve_topic_keywords(fresh, existing, keep=keep_keywords, everyday=everyday)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _finish(cls, topic_id: int, keywords: list[TopicKeywordWeightVo]) -> None:
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None or topic.status != RetrieveTopicStatus.GENERATING.value:
            return
        now = datetime.now()
        topic.status = RetrieveTopicStatus.READY.value
        topic.keyword_count = len(keywords)
        topic.error_message = None
        topic.update_time = now
        await RetrieveTopicDao.replace_keywords(topic.topic_id, keywords, now)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _mark_failed(cls, topic_id: int, message: str) -> None:
        topic = await RetrieveTopicDao.get_by_id(topic_id)
        if topic is None or topic.status != RetrieveTopicStatus.GENERATING.value:
            return
        topic.status = RetrieveTopicStatus.FAILED.value
        topic.error_message = message[:2000]
        topic.update_time = datetime.now()

    @classmethod
    async def _require_completed_task(cls, task_id: int) -> KnowledgeDocumentEmbeddingTask:
        task = await KnowledgeDocumentEmbeddingTaskDao.get_by_id(task_id)
        if task is None or task.status != EmbeddingTaskStatus.COMPLETED.value:
            raise ServiceException('请选择已完成的切分任务')
        return task

    @classmethod
    async def _extract(cls, task_id: int, everyday: frozenset[str]) -> list[TopicKeywordWeightVo]:
        segments = await RetrieveTopicDao.list_source_segments(task_id)
        texts = select_source_texts(segments)
        return await asyncio.to_thread(extract_topic_keywords, texts, everyday)

    @classmethod
    async def _to_detail(cls, topic: KnowledgeRetrieveTopic) -> RetrieveTopicDetailVo:
        document = await KnowledgeDocumentDao.get_document_by_id(topic.doc_id)
        rows: list[KnowledgeRetrieveTopicKeyword] = await RetrieveTopicDao.list_keywords(topic.topic_id)
        return RetrieveTopicDetailVo(
            topic_id=topic.topic_id,
            topic_name=topic.topic_name,
            description=topic.description,
            task_id=topic.task_id,
            doc_id=topic.doc_id,
            doc_title=document.doc_title if document else None,
            keyword_count=topic.keyword_count or 0,
            status=topic.status,
            error_message=topic.error_message,
            create_by=topic.create_by,
            create_time=topic.create_time,
            update_time=topic.update_time,
            keywords=[RetrieveTopicKeywordVo(keyword=row.keyword, weight=float(row.weight or 0)) for row in rows],
        )
