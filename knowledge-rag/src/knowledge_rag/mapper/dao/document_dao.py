from sqlalchemy import select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_rag.mapper.do.document_do import KnowledgeDocument


class KnowledgeDocumentDao:
    """
    文档主表数据库操作层
    """

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
    async def get_document_by_record_id(record_id: int) -> KnowledgeDocument | None:
        """
        根据上传记录ID获取文档

        :param record_id: 上传记录ID
        :return: 文档对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeDocument).where(
                        KnowledgeDocument.record_id == record_id, KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value  # type: ignore
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
            .values(is_latest='0')
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
