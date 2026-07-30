from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.embedding_task_status_enum import EmbeddingTaskStatus
from knowledge_content.enums.segment_status_enum import ReleaseTag
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_common.mapper.dao.base_dao import BaseDao


class KnowledgeDocumentEmbeddingTaskDao(BaseDao):
    """文档 Embedding 任务 DAO"""

    @staticmethod
    async def get_by_id(task_id: int) -> KnowledgeDocumentEmbeddingTask | None:
        """按主键取任务；populate_existing 避免同 session 内 UPDATE 后仍读到 identity map 旧状态。"""
        db: AsyncSession = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeDocumentEmbeddingTask)
                    .where(
                        KnowledgeDocumentEmbeddingTask.task_id == task_id,  # type: ignore
                        KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def add_task(task: KnowledgeDocumentEmbeddingTask) -> KnowledgeDocumentEmbeddingTask:
        db: AsyncSession = get_current_session()
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def has_in_progress(doc_id: int) -> bool:
        return await KnowledgeDocumentEmbeddingTaskDao.get_in_progress(doc_id) is not None

    @staticmethod
    async def get_in_progress(doc_id: int) -> KnowledgeDocumentEmbeddingTask | None:
        """同文档非终态任务（PENDING/CHUNKING/EMBEDDING），无则 None。"""
        db: AsyncSession = get_current_session()
        return (
            await db.execute(
                select(KnowledgeDocumentEmbeddingTask).where(
                    KnowledgeDocumentEmbeddingTask.doc_id == doc_id,  # type: ignore
                    KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    KnowledgeDocumentEmbeddingTask.status.in_(EmbeddingTaskStatus.in_progress_values()),  # type: ignore
                )
            )
        ).scalars().first()

    @staticmethod
    async def soft_delete(task_id: int, update_by: str = 'admin') -> None:
        db: AsyncSession = get_current_session()
        await db.execute(
            update(KnowledgeDocumentEmbeddingTask)
            .where(
                KnowledgeDocumentEmbeddingTask.task_id == task_id,  # type: ignore
                KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(
                del_flag=DeleteFlag.DELETED.value,
                update_by=update_by,
                update_time=datetime.now(),
            )
        )

    @staticmethod
    async def update_task(
        task_id: int,
        *,
        status: str | None = None,
        error_message: str | None = None,
        chunk_count: int | None = None,
        embedded_count: int | None = None,
        update_by: str | None = None,
    ) -> None:
        db: AsyncSession = get_current_session()
        values: dict[str, Any] = {'update_time': datetime.now()}
        if status is not None:
            values['status'] = status
        if error_message is not None:
            values['error_message'] = error_message[:2000]
        if chunk_count is not None:
            values['chunk_count'] = chunk_count
        if embedded_count is not None:
            values['embedded_count'] = embedded_count
        if update_by is not None:
            values['update_by'] = update_by
        await db.execute(
            update(KnowledgeDocumentEmbeddingTask)
            .where(
                KnowledgeDocumentEmbeddingTask.task_id == task_id,  # type: ignore
                KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(**values)
        )

    @staticmethod
    async def list_tasks(
        *,
        status: str | None = None,
        source_type: str | None = None,
        doc_id: int | None = None,
        doc_title: str | None = None,
        begin_time: datetime | None = None,
        end_time: datetime | None = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> PageModel:
        T = KnowledgeDocumentEmbeddingTask
        D = KnowledgeDocument
        query: Select[Any] = (
            select(
                T.task_id,
                T.doc_id,
                T.source_type,
                T.split_type,
                T.split_params,
                T.status,
                T.error_message,
                T.chunk_count,
                T.embedded_count,
                T.embedding_model_code,
                T.dimensions,
                T.user_id,
                T.create_by,
                T.create_time,
                T.update_time,
                D.doc_title,
            )
            .outerjoin(
                D,
                and_(
                    D.doc_id == T.doc_id,  # type: ignore
                    D.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                ),
            )
            .where(T.del_flag == DeleteFlag.NORMAL.value)  # type: ignore
        )
        if status:
            query = query.where(T.status == status)  # type: ignore
        if source_type:
            query = query.where(T.source_type == source_type)  # type: ignore
        if doc_id is not None:
            query = query.where(T.doc_id == doc_id)  # type: ignore
        if doc_title:
            query = query.where(D.doc_title.like(f'%{doc_title}%'))  # type: ignore
        if begin_time:
            query = query.where(T.create_time >= begin_time)  # type: ignore
        if end_time:
            query = query.where(T.create_time <= end_time)  # type: ignore
        query = query.order_by(T.task_id.desc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page=True)

    @staticmethod
    async def list_stale_pending(before: datetime, limit: int = 50) -> list[KnowledgeDocumentEmbeddingTask]:
        db: AsyncSession = get_current_session()
        rows: list[KnowledgeDocumentEmbeddingTask] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentEmbeddingTask)
                    .where(
                        KnowledgeDocumentEmbeddingTask.status == EmbeddingTaskStatus.PENDING.value,  # type: ignore
                        KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                        KnowledgeDocumentEmbeddingTask.update_time < before,  # type: ignore
                    )
                    .order_by(KnowledgeDocumentEmbeddingTask.task_id.asc())  # type: ignore
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    async def list_stuck_in_progress(before: datetime, limit: int = 50) -> list[KnowledgeDocumentEmbeddingTask]:
        db: AsyncSession = get_current_session()
        rows: list[KnowledgeDocumentEmbeddingTask] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentEmbeddingTask)
                    .where(
                        KnowledgeDocumentEmbeddingTask.status.in_(  # type: ignore
                            [
                                EmbeddingTaskStatus.CHUNKING.value,
                                EmbeddingTaskStatus.EMBEDDING.value,
                            ]
                        ),
                        KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                        KnowledgeDocumentEmbeddingTask.update_time < before,  # type: ignore
                    )
                    .order_by(KnowledgeDocumentEmbeddingTask.task_id.asc())  # type: ignore
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    async def list_failed_for_retry(limit: int = 50) -> list[KnowledgeDocumentEmbeddingTask]:
        db: AsyncSession = get_current_session()
        rows: list[KnowledgeDocumentEmbeddingTask] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentEmbeddingTask)
                    .where(
                        KnowledgeDocumentEmbeddingTask.status.in_(  # type: ignore
                            list(EmbeddingTaskStatus.failed_values())
                        ),
                        KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                    .order_by(KnowledgeDocumentEmbeddingTask.task_id.asc())  # type: ignore
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    async def aggregate_release_tags(task_ids: list[int]) -> dict[int, str | None]:
        """按 task_id 取任意一条 segment.release_tag（同任务应同标签）。

        每个 task 只 LIMIT 1，避免对十万级分段做 GROUP BY 全量扫描拖慢任务列表。
        """
        if not task_ids:
            return {}
        db: AsyncSession = get_current_session()
        result: dict[int, str | None] = {tid: None for tid in task_ids}
        for tid in task_ids:
            row = (
                await db.execute(
                    select(KnowledgeDocumentSegment.release_tag)
                    .where(
                        KnowledgeDocumentSegment.task_id == tid,  # type: ignore
                        KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                    .limit(1)
                )
            ).first()
            if row is not None:
                result[tid] = row[0]
        return result

    @staticmethod
    async def list_completed_canary_candidates(limit: int = 50) -> list[KnowledgeDocumentEmbeddingTask]:
        """临时发布：COMPLETED 且仍有 canary segment 的任务（同 doc 创建时已保证至多一套 canary）。"""
        db: AsyncSession = get_current_session()
        canary_task_ids = (
            select(KnowledgeDocumentSegment.task_id)
            .where(
                KnowledgeDocumentSegment.release_tag == ReleaseTag.CANARY.value,  # type: ignore
                KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .distinct()
        )
        rows: list[KnowledgeDocumentEmbeddingTask] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentEmbeddingTask)
                    .where(
                        KnowledgeDocumentEmbeddingTask.status == EmbeddingTaskStatus.COMPLETED.value,  # type: ignore
                        KnowledgeDocumentEmbeddingTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                        KnowledgeDocumentEmbeddingTask.task_id.in_(canary_task_ids),  # type: ignore
                    )
                    .order_by(KnowledgeDocumentEmbeddingTask.task_id.asc())  # type: ignore
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    def stale_before(minutes: int) -> datetime:
        return datetime.now() - timedelta(minutes=minutes)
