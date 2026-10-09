from sqlalchemy import exists, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.boolean_char_flag_enum import BooleanCharFlag
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.facade.api.knowledge_content.embedding_eval_vo import DocumentTitleItemVo
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.enums.segment_status_enum import ReleaseTag
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_common.mapper.dao.base_dao import BaseDao


class KnowledgeDocumentDao(BaseDao):
    """
    文档主表数据库操作层
    """

    @staticmethod
    async def get_crawl_document_list(
        task_id: int | None = None,
        doc_title: str | None = None,
        create_by: str | None = None,
        del_flag: str | None = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> PageModel:
        """
        分页查询爬取来源文档主表列表
        """
        query = select(KnowledgeDocument).where(
            KnowledgeDocument.source_type == DocumentSourceType.CRAWL.value,  # type: ignore
        )
        if del_flag is not None:
            query = query.where(KnowledgeDocument.del_flag == del_flag)  # type: ignore
        else:
            query = query.where(KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value)  # type: ignore
        if task_id is not None:
            query = query.where(KnowledgeDocument.task_id == task_id)  # type: ignore
        if doc_title is not None:
            query = query.where(KnowledgeDocument.doc_title.like(f'%{doc_title}%'))  # type: ignore
        if create_by is not None:
            query = query.where(KnowledgeDocument.create_by.like(f'%{create_by}%'))  # type: ignore
        query = query.order_by(KnowledgeDocument.doc_id.desc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page=True)

    @staticmethod
    async def list_options(keyword: str | None = None, limit: int = 50) -> list[KnowledgeDocument]:
        """已完成向量化、分段仍在的最新文档。已归档（分段已清）的不选出题。"""
        db = get_current_session()
        live_segments = exists(
            select(KnowledgeDocumentSegment.id).where(
                KnowledgeDocumentSegment.doc_id == KnowledgeDocument.doc_id,  # type: ignore
                KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                KnowledgeDocumentSegment.release_tag.in_(  # type: ignore
                    [ReleaseTag.CANARY.value, ReleaseTag.PROD.value]
                ),
            )
        )
        embedded = exists(
            select(KnowledgeDocumentEmbeddingTask.task_id).where(
                KnowledgeDocumentEmbeddingTask.doc_id == KnowledgeDocument.doc_id,  # type: ignore
                KnowledgeDocumentEmbeddingTask.status == EmbeddingTaskStatus.COMPLETED.value,  # type: ignore
                KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
        )
        query = select(KnowledgeDocument).where(
            KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            KnowledgeDocument.is_latest == BooleanCharFlag.YES.value,  # type: ignore
            embedded,
            live_segments,
        )
        if keyword:
            query = query.where(KnowledgeDocument.doc_title.like(f'%{keyword}%'))  # type: ignore
        query = query.order_by(KnowledgeDocument.doc_id.desc()).limit(limit)  # type: ignore
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def list_titles_by_ids(doc_ids: list[int]) -> list[DocumentTitleItemVo]:
        """按文档 ID 批量取标题，给测评任务列表展示。"""
        if not doc_ids:
            return []
        db = get_current_session()
        rows = await db.execute(
            select(KnowledgeDocument.doc_id, KnowledgeDocument.doc_title).where(
                KnowledgeDocument.doc_id.in_(doc_ids),  # type: ignore
                KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
        )
        return [
            DocumentTitleItemVo(doc_id=int(doc_id), doc_title=str(doc_title or ''))
            for doc_id, doc_title in rows.all()
        ]

    @staticmethod
    async def get_document_by_id(doc_id: int) -> KnowledgeDocument | None:
        """
        根据文档ID获取文档

        :param doc_id: 文档ID
        :return: 文档对象
        """
        db = get_current_session()
        return (
            (await db.execute(select(KnowledgeDocument).where(
                KnowledgeDocument.doc_id == doc_id, # type: ignore
                KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value  # type: ignore
            )))
            .scalars()
            .first()
        )

    @staticmethod
    async def get_document_by_task_id(task_id: int, source_type: str = '0') -> KnowledgeDocument | None:
        """
        根据任务ID获取文档

        :param task_id: 任务ID
        :param source_type: 来源类型（0-手动上传 1-网页爬取）
        :return: 文档对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.task_id == task_id,  # type: ignore
                        KnowledgeDocument.source_type == source_type,  # type: ignore
                        KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value  # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def add_document(document: KnowledgeDocument) -> KnowledgeDocument:
        """
        新增文档

        :param document: 文档对象
        :return: 文档对象
        """
        db = get_current_session()
        db.add(document)
        await db.flush()
        return document

    @staticmethod
    async def update_latest_by_title(doc_title: str, exclude_doc_id: int | None = None) -> None:
        """
        将同标题其他文档的 is_latest 更新为 '0'

        :param doc_title: 文档标题
        :param exclude_doc_id: 排除的文档ID
        :return:
        """
        db = get_current_session()
        query = (
            update(KnowledgeDocument)
            .where(
                KnowledgeDocument.doc_title == doc_title, # type: ignore
                KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value  # type: ignore
            )
            .values(is_latest=BooleanCharFlag.NO.value)
        )
        if exclude_doc_id:
            query = query.where(KnowledgeDocument.doc_id != exclude_doc_id)
        await db.execute(query)

    @staticmethod
    async def get_document_by_title_and_version(doc_title: str, doc_version: str) -> KnowledgeDocument | None:
        """
        根据文档标题和版本获取文档（用于判断重复，实现 upsert）

        :param doc_title: 文档标题
        :param doc_version: 文档版本
        :return: 文档对象
        """
        db = get_current_session()
        return (
            await db.execute(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.doc_title == doc_title,  # type: ignore
                    KnowledgeDocument.doc_version == doc_version,  # type: ignore
                    KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            )
        ).scalars().first()

    @staticmethod
    async def get_max_version_by_title(doc_title: str) -> str | None:
        """
        获取同标题已落库最大版本号

        :param doc_title: 文档标题
        :return: 最大版本号
        """
        db = get_current_session()
        result = (
            (
                await db.execute(
                    select(KnowledgeDocument.doc_version)
                    .where(KnowledgeDocument.doc_title == doc_title, KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value)  # type: ignore
                    .order_by(KnowledgeDocument.doc_version.desc())
                )
            )
            .scalars()
            .first()
        )
        return result
