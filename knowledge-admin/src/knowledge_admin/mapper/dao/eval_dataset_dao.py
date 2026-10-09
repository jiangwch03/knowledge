from datetime import datetime
from typing import Any

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.dao.base_dao import BaseDao
from knowledge_common.utils.page_util import PageUtil
from sqlalchemy import select, update
from sqlalchemy.orm import undefer

from knowledge_admin.enums.eval_dataset_status_enum import FAILED_STATUSES, IN_PROGRESS_STATUSES
from knowledge_admin.mapper.do.eval_do import KnowledgeEvalDataset, KnowledgeEvalDatasetItem
from knowledge_admin.vo.eval_vo import (
    EvalDatasetItemPageQueryModel,
    EvalDatasetNameVo,
    EvalDatasetPageQueryModel,
)

# 页面上的题目类型对应库存的 difficulty。旧数据仍是 RAGAS 合成器名。
_QUESTION_TYPE_VALUES = {
    'simple': ('simple', 'single_hop_specific_query_synthesizer'),
    'multi_hop': (
        'multi_hop',
        'multi_hop_specific_query_synthesizer',
        'multi_hop_abstract_query_synthesizer',
    ),
    'comprehensive': ('comprehensive',),
    'vague': ('vague',),
    'adversarial': ('adversarial',),
}


class EvalDatasetDao(BaseDao):
    """测评集 / 题目 DAO。"""

    @classmethod
    async def get_dataset_by_id(
        cls, dataset_id: int, *, with_material_plan: bool = False
    ) -> KnowledgeEvalDataset | None:
        db = get_current_session()
        query = select(KnowledgeEvalDataset).where(
            KnowledgeEvalDataset.dataset_id == dataset_id,
            KnowledgeEvalDataset.del_flag == DeleteFlag.NORMAL.value,
        )
        if with_material_plan:
            query = query.options(undefer(KnowledgeEvalDataset.material_plan))
        return (await db.execute(query)).scalars().first()

    @classmethod
    async def list_names_by_ids(cls, dataset_ids: list[int]) -> list[EvalDatasetNameVo]:
        """按测评集 ID 批量取名称。"""
        if not dataset_ids:
            return []
        db = get_current_session()
        rows = await db.execute(
            select(KnowledgeEvalDataset.dataset_id, KnowledgeEvalDataset.name).where(
                KnowledgeEvalDataset.dataset_id.in_(dataset_ids),
                KnowledgeEvalDataset.del_flag == DeleteFlag.NORMAL.value,
            )
        )
        return [
            EvalDatasetNameVo(dataset_id=int(dataset_id), name=str(name or ''))
            for dataset_id, name in rows.all()
        ]

    @classmethod
    async def get_dataset_list(
        cls, query_object: EvalDatasetPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        query = (
            select(KnowledgeEvalDataset)
            .where(
                KnowledgeEvalDataset.del_flag == DeleteFlag.NORMAL.value,
                KnowledgeEvalDataset.name.like(f'%{query_object.name}%') if query_object.name else True,
                KnowledgeEvalDataset.doc_id == query_object.doc_id if query_object.doc_id else True,
                KnowledgeEvalDataset.status == query_object.status if query_object.status else True,
            )
            .order_by(KnowledgeEvalDataset.dataset_id.desc())
        )
        return await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def insert_dataset(cls, dataset: KnowledgeEvalDataset) -> KnowledgeEvalDataset:
        db = get_current_session()
        db.add(dataset)
        await db.flush()
        return dataset

    @classmethod
    async def update_dataset(cls, values: dict[str, Any]) -> None:
        db = get_current_session()
        await db.execute(update(KnowledgeEvalDataset), [values])

    @classmethod
    async def get_item_by_id(cls, item_id: int) -> KnowledgeEvalDatasetItem | None:
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeEvalDatasetItem).where(
                        KnowledgeEvalDatasetItem.item_id == item_id,
                        KnowledgeEvalDatasetItem.del_flag == DeleteFlag.NORMAL.value,
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def list_items_by_dataset(
        cls,
        dataset_id: int,
        *,
        enabled_only: bool = False,
        query_object: EvalDatasetItemPageQueryModel | None = None,
        is_page: bool = False,
    ) -> PageModel | list[KnowledgeEvalDatasetItem]:
        db = get_current_session()
        conditions = [
            KnowledgeEvalDatasetItem.dataset_id == dataset_id,
            KnowledgeEvalDatasetItem.del_flag == DeleteFlag.NORMAL.value,
        ]
        if enabled_only:
            conditions.append(KnowledgeEvalDatasetItem.enabled == 1)
        if query_object is not None:
            question = (query_object.question or '').strip()
            if question:
                conditions.append(KnowledgeEvalDatasetItem.question.like(f'%{question}%'))
            difficulty = (query_object.difficulty or '').strip()
            if difficulty:
                values = _QUESTION_TYPE_VALUES.get(difficulty, (difficulty,))
                conditions.append(KnowledgeEvalDatasetItem.difficulty.in_(values))
            if query_object.enabled is not None:
                conditions.append(KnowledgeEvalDatasetItem.enabled == query_object.enabled)
        query = (
            select(KnowledgeEvalDatasetItem)
            .where(*conditions)
            .order_by(KnowledgeEvalDatasetItem.sort_order, KnowledgeEvalDatasetItem.item_id)
        )
        if is_page and query_object is not None:
            return await PageUtil.paginate(query, query_object.page_num, query_object.page_size, True)
        result = await db.execute(query)
        return list(result.scalars().all())

    @classmethod
    async def insert_items(cls, items: list[KnowledgeEvalDatasetItem]) -> None:
        if not items:
            return
        db = get_current_session()
        db.add_all(items)
        await db.flush()

    @classmethod
    async def update_item(cls, values: dict[str, Any]) -> None:
        db = get_current_session()
        await db.execute(update(KnowledgeEvalDatasetItem), [values])

    @classmethod
    async def soft_delete_items(cls, dataset_id: int, update_by: str) -> None:
        db = get_current_session()
        await db.execute(
            update(KnowledgeEvalDatasetItem)
            .where(
                KnowledgeEvalDatasetItem.dataset_id == dataset_id,
                KnowledgeEvalDatasetItem.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
        await db.flush()

    @classmethod
    async def list_stale_generating(cls, before: datetime) -> list[KnowledgeEvalDataset]:
        db = get_current_session()
        result = await db.execute(
            select(KnowledgeEvalDataset).where(
                KnowledgeEvalDataset.del_flag == DeleteFlag.NORMAL.value,
                KnowledgeEvalDataset.status.in_(IN_PROGRESS_STATUSES),
                KnowledgeEvalDataset.update_time < before,
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def list_failed(cls) -> list[KnowledgeEvalDataset]:
        """未删除且出题失败的测评集，供定时重试。"""
        db = get_current_session()
        result = await db.execute(
            select(KnowledgeEvalDataset).where(
                KnowledgeEvalDataset.del_flag == DeleteFlag.NORMAL.value,
                KnowledgeEvalDataset.status.in_(FAILED_STATUSES),
            )
        )
        return list(result.scalars().all())

    @classmethod
    async def soft_delete_dataset(cls, dataset_id: int, update_by: str) -> None:
        db = get_current_session()
        now = datetime.now()
        await db.execute(
            update(KnowledgeEvalDataset)
            .where(
                KnowledgeEvalDataset.dataset_id == dataset_id,
                KnowledgeEvalDataset.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=now)
        )
