from datetime import datetime

from sqlalchemy import select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_content.mapper.do.document_file_do import KnowledgeDocumentFile
from knowledge_common.mapper.dao.base_dao import BaseDao


class KnowledgeDocumentFileDao(BaseDao):
    """文档文件子表数据库操作层"""

    @staticmethod
    async def get_by_id(file_id: int) -> KnowledgeDocumentFile | None:
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeDocumentFile).where(
                        KnowledgeDocumentFile.id == file_id,  # type: ignore
                        KnowledgeDocumentFile.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def list_by_doc_id(doc_id: int) -> list[KnowledgeDocumentFile]:
        db = get_current_session()
        result = await db.execute(
            select(KnowledgeDocumentFile)
            .where(
                KnowledgeDocumentFile.doc_id == doc_id,  # type: ignore
                KnowledgeDocumentFile.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .order_by(KnowledgeDocumentFile.id.asc())  # type: ignore
        )
        return list(result.scalars().all())

    @staticmethod
    async def list_by_doc_ids(doc_ids: list[int]) -> list[KnowledgeDocumentFile]:
        """按多个 doc_id 批量查询文件行（id 升序）"""
        if not doc_ids:
            return []
        db = get_current_session()
        result = await db.execute(
            select(KnowledgeDocumentFile)
            .where(
                KnowledgeDocumentFile.doc_id.in_(doc_ids),  # type: ignore
                KnowledgeDocumentFile.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .order_by(KnowledgeDocumentFile.id.asc())  # type: ignore
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_first_by_doc_id(doc_id: int) -> KnowledgeDocumentFile | None:
        files = await KnowledgeDocumentFileDao.list_by_doc_id(doc_id)
        return files[0] if files else None

    @staticmethod
    async def list_by_ids(file_ids: list[int], doc_id: int | None = None) -> list[KnowledgeDocumentFile]:
        if not file_ids:
            return []
        db = get_current_session()
        query = select(KnowledgeDocumentFile).where(
            KnowledgeDocumentFile.id.in_(file_ids),  # type: ignore
            KnowledgeDocumentFile.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        )
        if doc_id is not None:
            query = query.where(KnowledgeDocumentFile.doc_id == doc_id)  # type: ignore
        query = query.order_by(KnowledgeDocumentFile.id.asc())  # type: ignore
        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def add_file(file_row: KnowledgeDocumentFile) -> KnowledgeDocumentFile:
        db = get_current_session()
        db.add(file_row)
        await db.flush()
        return file_row

    @staticmethod
    async def add_files(file_rows: list[KnowledgeDocumentFile]) -> list[KnowledgeDocumentFile]:
        if not file_rows:
            return []
        db = get_current_session()
        db.add_all(file_rows)
        await db.flush()
        return file_rows

    @staticmethod
    async def soft_delete_by_doc_id(doc_id: int, update_by: str = '') -> None:
        db = get_current_session()
        await db.execute(
            update(KnowledgeDocumentFile)
            .where(
                KnowledgeDocumentFile.doc_id == doc_id,  # type: ignore
                KnowledgeDocumentFile.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(
                del_flag=DeleteFlag.DELETED.value,
                update_by=update_by,
                update_time=datetime.now(),
            )
        )
