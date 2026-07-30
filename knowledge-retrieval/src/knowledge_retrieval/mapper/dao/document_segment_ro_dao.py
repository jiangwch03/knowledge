from sqlalchemy import select

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_retrieval.mapper.do.document_segment_ro_do import KnowledgeDocumentSegmentRo
from knowledge_common.mapper.dao.base_dao import BaseDao


class DocumentSegmentRoDao(BaseDao):
    """分段只读查询（父片回填）。"""

    @staticmethod
    async def get_by_chunk_ids(chunk_ids: list[str]) -> dict[str, KnowledgeDocumentSegmentRo]:
        if not chunk_ids:
            return {}
        db = get_current_session()
        rows = (
            await db.execute(
                select(KnowledgeDocumentSegmentRo).where(
                    KnowledgeDocumentSegmentRo.chunk_id.in_(chunk_ids),
                    KnowledgeDocumentSegmentRo.del_flag == DeleteFlag.NORMAL.value,
                )
            )
        ).scalars().all()
        return {row.chunk_id: row for row in rows if row.chunk_id}
