from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update

from knowledge_admin.mapper.do.eval_do import KnowledgeEvalRun, KnowledgeEvalRunItem, KnowledgeEvalTask
from knowledge_admin.vo.eval_vo import EvalRunPageQueryModel, EvalTaskPageQueryModel
from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.mapper.dao.base_dao import BaseDao
from knowledge_common.utils.page_util import PageUtil


class EvalTaskDao(BaseDao):
    """测评任务 / run / run_item DAO。"""

    @classmethod
    async def get_task_by_id(cls, eval_task_id: int) -> KnowledgeEvalTask | None:
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeEvalTask).where(
                        KnowledgeEvalTask.eval_task_id == eval_task_id,
                        KnowledgeEvalTask.del_flag == DeleteFlag.NORMAL.value,
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def get_task_list(
        cls, query_object: EvalTaskPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        query = (
            select(KnowledgeEvalTask)
            .where(
                KnowledgeEvalTask.del_flag == DeleteFlag.NORMAL.value,
                KnowledgeEvalTask.doc_id == query_object.doc_id if query_object.doc_id else True,
                KnowledgeEvalTask.dataset_id == query_object.dataset_id if query_object.dataset_id else True,
                KnowledgeEvalTask.status == query_object.status if query_object.status else True,
                KnowledgeEvalTask.embedding_task_id == query_object.embedding_task_id
                if query_object.embedding_task_id
                else True,
                KnowledgeEvalTask.name.like(f'%{query_object.name}%') if query_object.name else True,
            )
            .order_by(KnowledgeEvalTask.eval_task_id.desc())
        )
        return await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def insert_task(cls, task: KnowledgeEvalTask) -> KnowledgeEvalTask:
        db = get_current_session()
        db.add(task)
        await db.flush()
        return task

    @classmethod
    async def update_task(cls, values: dict[str, Any]) -> None:
        db = get_current_session()
        await db.execute(update(KnowledgeEvalTask), [values])

    @classmethod
    async def insert_run(cls, run: KnowledgeEvalRun) -> KnowledgeEvalRun:
        db = get_current_session()
        db.add(run)
        await db.flush()
        return run

    @classmethod
    async def update_run(cls, values: dict[str, Any]) -> None:
        db = get_current_session()
        await db.execute(update(KnowledgeEvalRun), [values])

    @classmethod
    async def get_run_by_id(cls, run_id: int) -> KnowledgeEvalRun | None:
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeEvalRun).where(
                        KnowledgeEvalRun.run_id == run_id,
                        KnowledgeEvalRun.del_flag == DeleteFlag.NORMAL.value,
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def list_unfinished_runs(cls, eval_task_id: int) -> list[KnowledgeEvalRun]:
        """还没结束的执行，新的在前。"""
        db = get_current_session()
        result = await db.execute(
            select(KnowledgeEvalRun)
            .where(
                KnowledgeEvalRun.eval_task_id == eval_task_id,
                KnowledgeEvalRun.status.in_(('PENDING', 'RUNNING')),
                KnowledgeEvalRun.del_flag == DeleteFlag.NORMAL.value,
            )
            .order_by(KnowledgeEvalRun.run_id.desc())
        )
        return list(result.scalars().all())

    @classmethod
    async def list_runs(
        cls, query_object: EvalRunPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        query = (
            select(KnowledgeEvalRun)
            .where(
                KnowledgeEvalRun.del_flag == DeleteFlag.NORMAL.value,
                KnowledgeEvalRun.eval_task_id == query_object.eval_task_id
                if query_object.eval_task_id
                else True,
            )
            .order_by(KnowledgeEvalRun.run_id.desc())
        )
        return await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def count_success_runs(cls, eval_task_id: int) -> int:
        db = get_current_session()
        result = await db.execute(
            select(func.count())
            .select_from(KnowledgeEvalRun)
            .where(
                KnowledgeEvalRun.eval_task_id == eval_task_id,
                KnowledgeEvalRun.status == 'SUCCESS',
                KnowledgeEvalRun.del_flag == DeleteFlag.NORMAL.value,
            )
        )
        return int(result.scalar_one() or 0)

    @classmethod
    async def insert_run_items(cls, items: list[KnowledgeEvalRunItem]) -> None:
        if not items:
            return
        db = get_current_session()
        db.add_all(items)
        await db.flush()

    @classmethod
    async def list_run_items(cls, run_id: int) -> list[KnowledgeEvalRunItem]:
        db = get_current_session()
        result = await db.execute(
            select(KnowledgeEvalRunItem)
            .where(
                KnowledgeEvalRunItem.run_id == run_id,
                KnowledgeEvalRunItem.del_flag == DeleteFlag.NORMAL.value,
            )
            .order_by(KnowledgeEvalRunItem.sort_order, KnowledgeEvalRunItem.run_item_id)
        )
        return list(result.scalars().all())

    @classmethod
    async def soft_delete_task(cls, eval_task_id: int, update_by: str) -> None:
        db = get_current_session()
        now = datetime.now()
        await db.execute(
            update(KnowledgeEvalTask)
            .where(
                KnowledgeEvalTask.eval_task_id == eval_task_id,
                KnowledgeEvalTask.del_flag == DeleteFlag.NORMAL.value,
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=now)
        )
