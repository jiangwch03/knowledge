from datetime import datetime
from typing import Any

from sqlalchemy import Select, case, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.segment_status_enum import ReleaseTag, SegmentArchiveReason, SegmentStatus
from knowledge_content.mapper.do.document_segment_archive_do import KnowledgeDocumentSegmentArchive
from knowledge_content.mapper.do.document_segment_do import KnowledgeDocumentSegment
from knowledge_common.mapper.dao.base_dao import BaseDao


class KnowledgeDocumentSegmentDao(BaseDao):
    """文档分段 DAO"""

    @staticmethod
    async def bulk_insert(segments: list[KnowledgeDocumentSegment]) -> None:
        if not segments:
            return
        db: AsyncSession = get_current_session()
        db.add_all(segments)
        await db.flush()

    @staticmethod
    async def has_canary_by_doc(doc_id: int) -> bool:
        """同文档是否存在未删除的 canary segment（未发布）"""
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(KnowledgeDocumentSegment.task_id).where(
                    KnowledgeDocumentSegment.doc_id == doc_id,  # type: ignore
                    KnowledgeDocumentSegment.release_tag == ReleaseTag.CANARY.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                ).limit(1)
            )
        ).first()
        return row is not None

    @staticmethod
    async def has_prod_by_task(task_id: int) -> bool:
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(KnowledgeDocumentSegment.id).where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.release_tag == ReleaseTag.PROD.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                ).limit(1)
            )
        ).first()
        return row is not None

    @staticmethod
    async def has_segments_by_task(task_id: int) -> bool:
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(KnowledgeDocumentSegment.id).where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                ).limit(1)
            )
        ).first()
        return row is not None

    @staticmethod
    async def list_file_ids_by_task(task_id: int) -> set[int]:
        """本任务已切分落库的 file_id 集合（用于跳过已完成文件）。"""
        db: AsyncSession = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeDocumentSegment.file_id)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .distinct()
            )
        ).scalars().all()
        return {int(fid) for fid in rows if fid is not None}

    @staticmethod
    async def count_by_task(task_id: int, *, skip_embedding: int | None = None) -> int:
        db: AsyncSession = get_current_session()
        conditions = [
            KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
            KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        ]
        if skip_embedding is not None:
            conditions.append(KnowledgeDocumentSegment.skip_embedding == skip_embedding)  # type: ignore
        row = (
            await db.execute(
                select(func.count()).select_from(KnowledgeDocumentSegment).where(*conditions)
            )
        ).scalar_one()
        return int(row or 0)

    @staticmethod
    def _to_archive(
        segment: KnowledgeDocumentSegment,
        *,
        archive_by: str,
        archive_reason: str,
        archive_time: datetime,
    ) -> KnowledgeDocumentSegmentArchive:
        return KnowledgeDocumentSegmentArchive(
            id=segment.id,
            task_id=segment.task_id,
            doc_id=segment.doc_id,
            file_id=segment.file_id,
            chunk_id=segment.chunk_id,
            chunk_order=segment.chunk_order,
            text=segment.text,
            metadata_json=segment.metadata_json,
            parent_chunk_id=segment.parent_chunk_id,
            skip_embedding=segment.skip_embedding,
            embedding_id=segment.embedding_id,
            embedding_vector=segment.embedding_vector,
            status=segment.status,
            release_tag=segment.release_tag,
            create_by=segment.create_by,
            create_time=segment.create_time,
            update_by=segment.update_by,
            update_time=segment.update_time,
            del_flag=segment.del_flag,
            archive_time=archive_time,
            archive_by=archive_by,
            archive_reason=archive_reason,
        )

    @staticmethod
    async def _archive_and_delete(
        segments: list[KnowledgeDocumentSegment],
        *,
        archive_by: str,
        archive_reason: str,
    ) -> int:
        """先写入归档表，再物理删除主表行；返回删除条数。重试时覆盖同 id 归档行。"""
        if not segments:
            return 0
        db: AsyncSession = get_current_session()
        now: datetime = datetime.now()
        segment_ids: list[int] = [int(s.id) for s in segments]
        # 清理上次崩溃留下的同 id 归档，保证可重入
        await db.execute(
            delete(KnowledgeDocumentSegmentArchive).where(
                KnowledgeDocumentSegmentArchive.id.in_(segment_ids)  # type: ignore
            )
        )
        db.add_all(
            [
                KnowledgeDocumentSegmentDao._to_archive(
                    s,
                    archive_by=archive_by,
                    archive_reason=archive_reason,
                    archive_time=now,
                )
                for s in segments
            ]
        )
        await db.flush()
        result = await db.execute(
            delete(KnowledgeDocumentSegment).where(
                KnowledgeDocumentSegment.id.in_(segment_ids)  # type: ignore
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    async def archive_and_delete_by_task(
        task_id: int,
        *,
        archive_by: str = 'admin',
        archive_reason: str = SegmentArchiveReason.TASK_RESIDUE.value,
    ) -> int:
        """任务残留清理：归档本任务全部分片后物理删除。"""
        db: AsyncSession = get_current_session()
        segments: list[KnowledgeDocumentSegment] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentSegment)
                    .options(undefer(KnowledgeDocumentSegment.embedding_vector))
                    .where(KnowledgeDocumentSegment.task_id == task_id)  # type: ignore
                )
            )
            .scalars()
            .all()
        )
        return await KnowledgeDocumentSegmentDao._archive_and_delete(
            segments,
            archive_by=archive_by,
            archive_reason=archive_reason,
        )

    @staticmethod
    async def archive_and_delete_by_ids(
        segment_ids: list[int],
        *,
        archive_by: str = 'admin',
        archive_reason: str = SegmentArchiveReason.PENDING_DELETE_CLEANUP.value,
    ) -> int:
        """按 id 归档后物理删除（含 embedding_vector，便于恢复）。"""
        if not segment_ids:
            return 0
        db: AsyncSession = get_current_session()
        segments: list[KnowledgeDocumentSegment] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentSegment)
                    .options(undefer(KnowledgeDocumentSegment.embedding_vector))
                    .where(KnowledgeDocumentSegment.id.in_(segment_ids))  # type: ignore
                )
            )
            .scalars()
            .all()
        )
        return await KnowledgeDocumentSegmentDao._archive_and_delete(
            segments,
            archive_by=archive_by,
            archive_reason=archive_reason,
        )

    @staticmethod
    async def list_task_ids_by_doc_and_tag(doc_id: int, release_tag: str) -> list[int]:
        """同文档指定 release_tag 的未删除 task_id（去重）。"""
        db: AsyncSession = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeDocumentSegment.task_id)
                .where(
                    KnowledgeDocumentSegment.doc_id == doc_id,  # type: ignore
                    KnowledgeDocumentSegment.release_tag == release_tag,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .distinct()
            )
        ).scalars().all()
        return [int(tid) for tid in rows if tid is not None]

    @staticmethod
    async def update_release_tag_by_task(
        task_id: int,
        *,
        from_tag: str,
        to_tag: str,
        update_by: str = 'admin',
    ) -> int:
        """按 task_id 将指定 from_tag 的 segment 切到 to_tag；返回影响行数。"""
        db: AsyncSession = get_current_session()
        result = await db.execute(
            update(KnowledgeDocumentSegment)
            .where(
                KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                KnowledgeDocumentSegment.release_tag == from_tag,  # type: ignore
                KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(
                release_tag=to_tag,
                update_by=update_by,
                update_time=datetime.now(),
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    async def update_release_tag_by_doc_excluding_task(
        doc_id: int,
        *,
        exclude_task_id: int,
        from_tags: list[str],
        to_tag: str,
        update_by: str = 'admin',
    ) -> int:
        """同 doc 下非目标任务、且标签在 from_tags 的 segment → to_tag。"""
        if not from_tags:
            return 0
        db: AsyncSession = get_current_session()
        result = await db.execute(
            update(KnowledgeDocumentSegment)
            .where(
                KnowledgeDocumentSegment.doc_id == doc_id,  # type: ignore
                KnowledgeDocumentSegment.task_id != exclude_task_id,  # type: ignore
                KnowledgeDocumentSegment.release_tag.in_(from_tags),  # type: ignore
                KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(
                release_tag=to_tag,
                update_by=update_by,
                update_time=datetime.now(),
            )
        )
        return int(result.rowcount or 0)

    @staticmethod
    async def list_embedding_ids_by_task(
        task_id: int,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[str]:
        """本任务已写入向量库的 embedding_id（不含向量本体）。"""
        db: AsyncSession = get_current_session()
        query = (
            select(KnowledgeDocumentSegment.embedding_id)
            .where(
                KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                KnowledgeDocumentSegment.status == SegmentStatus.VECTOR_STORED.value,  # type: ignore
                KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                KnowledgeDocumentSegment.embedding_id.is_not(None),  # type: ignore
            )
            .order_by(
                KnowledgeDocumentSegment.file_id.asc(),  # type: ignore
                KnowledgeDocumentSegment.chunk_order.asc(),  # type: ignore
            )
            .offset(offset)
        )
        if limit is not None:
            query = query.limit(limit)
        rows = (await db.execute(query)).scalars().all()
        return [str(eid) for eid in rows if eid]

    @staticmethod
    async def list_pending_delete_for_cleanup(limit: int) -> list[KnowledgeDocumentSegment]:
        """待异步清理的 pending_delete 分片（优先有 embedding_id 的）。"""
        db: AsyncSession = get_current_session()
        return list(
            (
                await db.execute(
                    select(KnowledgeDocumentSegment)
                    .where(
                        KnowledgeDocumentSegment.release_tag == ReleaseTag.PENDING_DELETE.value,  # type: ignore
                        KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                    .order_by(KnowledgeDocumentSegment.id.asc())  # type: ignore
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    async def count_pending_embed_by_task(task_id: int) -> int:
        """待 Embedding 分片数：skip_embedding=0 且 status=STORED。"""
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(func.count())
                .select_from(KnowledgeDocumentSegment)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                    KnowledgeDocumentSegment.status == SegmentStatus.STORED.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            )
        ).scalar_one()
        return int(row or 0)

    @staticmethod
    async def list_pending_embed_by_task(task_id: int, limit: int) -> list[KnowledgeDocumentSegment]:
        """待调用 Embedding 的分片：skip_embedding=0 且 status=STORED（向量未落库），按 limit 取一批。

        不按 offset 分页：处理完会推进为 EMBEDDED，离开结果集；固定取剩余队列头部即可。
        """
        db: AsyncSession = get_current_session()
        rows: list[KnowledgeDocumentSegment] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentSegment)
                    .where(
                        KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                        KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                        KnowledgeDocumentSegment.status == SegmentStatus.STORED.value,  # type: ignore
                        KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                    .order_by(
                        KnowledgeDocumentSegment.file_id.asc(),  # type: ignore
                        KnowledgeDocumentSegment.chunk_order.asc(),  # type: ignore
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    async def list_pending_embed_ids_by_task(task_id: int) -> list[int]:
        """待 Embedding 的全部分片 id（仅主键，供队列并发领取）。"""
        db: AsyncSession = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeDocumentSegment.id)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                    KnowledgeDocumentSegment.status == SegmentStatus.STORED.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .order_by(
                    KnowledgeDocumentSegment.file_id.asc(),  # type: ignore
                    KnowledgeDocumentSegment.chunk_order.asc(),  # type: ignore
                )
            )
        ).scalars().all()
        return [int(i) for i in rows]

    @staticmethod
    async def list_by_ids(
        ids: list[int],
        *,
        with_embedding_vector: bool = False,
    ) -> list[KnowledgeDocumentSegment]:
        """按主键批量加载；保持传入 id 顺序。"""
        if not ids:
            return []
        db: AsyncSession = get_current_session()
        query = select(KnowledgeDocumentSegment).where(
            KnowledgeDocumentSegment.id.in_(ids)  # type: ignore
        )
        if with_embedding_vector:
            query = query.options(undefer(KnowledgeDocumentSegment.embedding_vector))
        rows: list[KnowledgeDocumentSegment] = list((await db.execute(query)).scalars().all())
        by_id: dict[int, KnowledgeDocumentSegment] = {int(r.id): r for r in rows}
        return [by_id[i] for i in ids if i in by_id]

    @staticmethod
    async def count_pending_milvus_by_task(task_id: int) -> int:
        """待刷 Milvus 分片数：skip_embedding=0 且 status=EMBEDDED。"""
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(func.count())
                .select_from(KnowledgeDocumentSegment)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                    KnowledgeDocumentSegment.status == SegmentStatus.EMBEDDED.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            )
        ).scalar_one()
        return int(row or 0)

    @staticmethod
    async def list_pending_milvus_by_task(task_id: int, limit: int) -> list[KnowledgeDocumentSegment]:
        """待刷 Milvus 的分片：status=EMBEDDED，并加载 embedding_vector，按 limit 取一批。

        同 list_pending_embed_by_task：处理后离开结果集，不做 offset。
        """
        db: AsyncSession = get_current_session()
        rows: list[KnowledgeDocumentSegment] = list(
            (
                await db.execute(
                    select(KnowledgeDocumentSegment)
                    .options(undefer(KnowledgeDocumentSegment.embedding_vector))
                    .where(
                        KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                        KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                        KnowledgeDocumentSegment.status == SegmentStatus.EMBEDDED.value,  # type: ignore
                        KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    )
                    .order_by(
                        KnowledgeDocumentSegment.file_id.asc(),  # type: ignore
                        KnowledgeDocumentSegment.chunk_order.asc(),  # type: ignore
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows

    @staticmethod
    async def list_pending_milvus_ids_by_task(task_id: int) -> list[int]:
        """待刷 Milvus 的全部分片 id（仅主键，供队列并发领取）。"""
        db: AsyncSession = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeDocumentSegment.id)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                    KnowledgeDocumentSegment.status == SegmentStatus.EMBEDDED.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .order_by(
                    KnowledgeDocumentSegment.file_id.asc(),  # type: ignore
                    KnowledgeDocumentSegment.chunk_order.asc(),  # type: ignore
                )
            )
        ).scalars().all()
        return [int(i) for i in rows]

    @staticmethod
    async def count_vector_stored_by_task(task_id: int) -> int:
        """本任务已成功写入 Milvus 的分片数（skip_embedding=0 且 VECTOR_STORED）。"""
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(func.count())
                .select_from(KnowledgeDocumentSegment)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                    KnowledgeDocumentSegment.status == SegmentStatus.VECTOR_STORED.value,  # type: ignore
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            )
        ).scalar_one()
        return int(row or 0)

    @staticmethod
    async def update_embedded(segment_id: int, embedding_vector: bytes) -> None:
        """落库向量并推进为 EMBEDDED。"""
        await KnowledgeDocumentSegmentDao.batch_update_embedded([(segment_id, embedding_vector)])

    @staticmethod
    async def batch_update_embedded(items: list[tuple[int, bytes]]) -> None:
        """批量落库向量并推进为 EMBEDDED（单条 SQL CASE WHEN，避免逐行 round-trip）。"""
        if not items:
            return
        db: AsyncSession = get_current_session()
        ids: list[int] = [segment_id for segment_id, _ in items]
        now: datetime = datetime.now()
        await db.execute(
            update(KnowledgeDocumentSegment)
            .where(KnowledgeDocumentSegment.id.in_(ids))  # type: ignore
            .values(
                embedding_vector=case(
                    {segment_id: embedding_vector for segment_id, embedding_vector in items},
                    value=KnowledgeDocumentSegment.id,
                ),
                status=SegmentStatus.EMBEDDED.value,
                update_time=now,
            )
        )

    @staticmethod
    async def update_vector_stored(segment_id: int, embedding_id: str) -> None:
        """Milvus 写入成功后回写 embedding_id，并推进为 VECTOR_STORED。"""
        await KnowledgeDocumentSegmentDao.batch_update_vector_stored([(segment_id, embedding_id)])

    @staticmethod
    async def batch_update_vector_stored(items: list[tuple[int, str]]) -> None:
        """批量回写 embedding_id 并推进为 VECTOR_STORED。"""
        if not items:
            return
        db: AsyncSession = get_current_session()
        ids: list[int] = [segment_id for segment_id, _ in items]
        now: datetime = datetime.now()
        await db.execute(
            update(KnowledgeDocumentSegment)
            .where(KnowledgeDocumentSegment.id.in_(ids))  # type: ignore
            .values(
                embedding_id=case(
                    {segment_id: embedding_id for segment_id, embedding_id in items},
                    value=KnowledgeDocumentSegment.id,
                ),
                status=SegmentStatus.VECTOR_STORED.value,
                update_time=now,
            )
        )

    @staticmethod
    async def count_embed_progress_by_task(task_id: int) -> int:
        """向量化进度：skip_embedding=0 且已离开 STORED（EMBEDDED + VECTOR_STORED）。"""
        db: AsyncSession = get_current_session()
        row = (
            await db.execute(
                select(func.count())
                .select_from(KnowledgeDocumentSegment)
                .where(
                    KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
                    KnowledgeDocumentSegment.skip_embedding == 0,  # type: ignore
                    KnowledgeDocumentSegment.status.in_(  # type: ignore
                        [
                            SegmentStatus.EMBEDDED.value,
                            SegmentStatus.VECTOR_STORED.value,
                        ]
                    ),
                    KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            )
        ).scalar_one()
        return int(row or 0)

    @staticmethod
    async def list_by_task_page(
        task_id: int,
        *,
        skip_embedding: int | None = None,
        page_num: int = 1,
        page_size: int = 20,
    ) -> PageModel:
        query: Select[Any] = select(KnowledgeDocumentSegment).where(
            KnowledgeDocumentSegment.task_id == task_id,  # type: ignore
            KnowledgeDocumentSegment.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        )
        if skip_embedding is not None:
            query = query.where(KnowledgeDocumentSegment.skip_embedding == skip_embedding)  # type: ignore
        query = query.order_by(
            KnowledgeDocumentSegment.file_id.asc(),  # type: ignore
            KnowledgeDocumentSegment.chunk_order.asc(),  # type: ignore
        )
        return await PageUtil.paginate(query, page_num, page_size, is_page=True)
