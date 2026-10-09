"""测评集：创建即落库并投递生成消息，人工只改题。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.config.env import EvalDatasetConfig, StreamTopicConfig
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.log_util import logger

from knowledge_admin.enums.eval_dataset_status_enum import EvalDatasetStatus
from knowledge_admin.mapper.dao.eval_dataset_dao import EvalDatasetDao
from knowledge_admin.mapper.do.eval_do import KnowledgeEvalDataset, KnowledgeEvalDatasetItem
from knowledge_admin.service.vo.eval_dataset_message_vo import EvalDatasetPending
from knowledge_admin.vo.eval_vo import (
    EvalDatasetCreateVo,
    EvalDatasetDetailVo,
    EvalDatasetItemModel,
    EvalDatasetItemPageQueryModel,
    EvalDatasetItemUpdateVo,
    EvalDatasetModel,
    EvalDatasetPageQueryModel,
    GeneratedDatasetItemVo,
)

if TYPE_CHECKING:
    from knowledge_common.vo.user_vo import CurrentUserModel

    from knowledge_admin.vo.eval_question_plan_vo import EvalDatasetMaterialRecordVo


class EvalDatasetService:
    """测评集服务。"""

    @classmethod
    async def create_dataset(
        cls,
        vo: EvalDatasetCreateVo,
        current_user: CurrentUserModel,
    ) -> EvalDatasetModel:
        if vo.question_count < 50:  # noqa: PLR2004
            raise ServiceException(message='题目数量至少 50')
        # 步骤1：创建测评集，绑定文档，题目尚未生成
        dataset = await cls._insert_dataset(vo, current_user)
        dataset_id = int(dataset.dataset_id)
        # 步骤2：异步触发出题，生成完成后人工只改题
        await cls.publish_pending(dataset_id)
        return EvalDatasetModel(**CamelCaseUtil.transform_result(dataset))

    @classmethod
    @transactional()
    async def _insert_dataset(
        cls,
        vo: EvalDatasetCreateVo,
        current_user: CurrentUserModel,
    ) -> KnowledgeEvalDataset:
        now = datetime.now()
        user_name = current_user.user.user_name
        dataset = KnowledgeEvalDataset(
            name=vo.name.strip(),  # 测评集名称
            doc_id=vo.doc_id,  # 绑定文档，出题和后续测评都按这份文档
            description=vo.description,  # 描述
            status=EvalDatasetStatus.INIT.value,  # 初始化，出题从圈资料开始
            item_count=0,  # 已生成题目数，出题完成前为 0
            question_count=vo.question_count,  # 本次要求生成的题目数
            user_id=current_user.user.user_id,  # 所属用户
            dept_id=current_user.user.dept_id,  # 所属部门
            create_by=user_name,  # 创建人
            create_time=now,
            update_by=user_name,  # 首次创建时更新人与创建人相同
            update_time=now,
            del_flag=DeleteFlag.NORMAL.value,  # 未删除
        )
        return await EvalDatasetDao.insert_dataset(dataset)

    @classmethod
    async def publish_pending(cls, dataset_id: int) -> None:
        try:
            await MessageStreamService.produce(
                topic=StreamTopicConfig.eval_dataset_pending,
                value=EvalDatasetPending(dataset_id=dataset_id).model_dump(by_alias=True),
                key=str(dataset_id),
            )
        except Exception as exc:
            err = format_exception_message(exc)
            logger.exception('发布 eval.dataset.pending 失败 dataset_id={} error={}', dataset_id, err)
            raise ServiceException(message=f'发布测评集生成消息失败: {err}') from exc

    @classmethod
    async def repost_stale(cls) -> None:
        """定时兜底：还没到可测评、超时且当前没有执行锁时重新投递。"""
        before = datetime.now() - timedelta(minutes=EvalDatasetConfig.eval_dataset_stale_minutes)
        rows = await cls._list_stale(before)
        for dataset_id in rows:
            lock_key = LockKey.eval_dataset_key(dataset_id)
            try:
                async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
                    if not acquired:
                        continue
                await cls.publish_pending(dataset_id)
                logger.info('[EvalDataset] 兜底重投递 dataset_id={}', dataset_id)
            except Exception as exc:
                logger.exception('[EvalDataset] 兜底重投递失败 dataset_id={} error={}', dataset_id, exc)

    @classmethod
    async def retry_failed(cls) -> None:
        """定时重试：停在失败状态的测评集清掉备注再投递。状态留在失败的那一步。"""
        rows = await cls._list_failed()
        for dataset in rows:
            dataset_id = int(dataset.dataset_id)
            lock_key = LockKey.eval_dataset_key(dataset_id)
            try:
                async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
                    if not acquired:
                        continue
                update_by = dataset.update_by or ''
                await cls._mark_status(dataset_id, dataset.status, update_by, remark='')
                try:
                    await cls.publish_pending(dataset_id)
                except Exception:
                    await cls.mark_failed(dataset_id, '重新出题投递失败', update_by)
                    raise
                logger.info('[EvalDataset] 出题失败，重新出题 dataset_id={}', dataset_id)
            except Exception as exc:
                logger.exception('[EvalDataset] 失败重试投递失败 dataset_id={} error={}', dataset_id, exc)

    @classmethod
    @transactional()
    async def _list_stale(cls, before: datetime) -> list[int]:
        datasets = await EvalDatasetDao.list_stale_generating(before)
        return [int(row.dataset_id) for row in datasets]

    @classmethod
    @transactional()
    async def _list_failed(cls) -> list[KnowledgeEvalDataset]:
        return await EvalDatasetDao.list_failed()

    @classmethod
    @transactional()
    async def load_generating(cls, dataset_id: int) -> KnowledgeEvalDataset | None:
        return await EvalDatasetDao.get_dataset_by_id(dataset_id, with_material_plan=True)

    @classmethod
    async def touch_generating(cls, dataset_id: int, update_by: str) -> None:
        """只刷新更新时间，避免长时间出题被当成卡住。不改当前状态。"""
        await cls._touch(dataset_id, update_by)

    @classmethod
    async def mark_failed(cls, dataset_id: int, remark: str, update_by: str) -> None:
        try:
            await cls._touch(dataset_id, update_by, remark=remark[:480])
        except Exception:
            logger.opt(exception=True).error('标记出题失败 dataset_id={}', dataset_id)

    @classmethod
    async def mark_stage_failed(cls, dataset_id: int, stage: str, remark: str, update_by: str) -> None:
        """当前步骤失败。已完成步骤和题目保留。"""
        try:
            await cls._mark_status(dataset_id, stage, update_by, remark=remark[:480])
        except Exception:
            logger.opt(exception=True).error('标记出题阶段失败 dataset_id={} stage={}', dataset_id, stage)

    @classmethod
    async def save_material(cls, dataset_id: int, record: EvalDatasetMaterialRecordVo, update_by: str) -> None:
        await cls._save_material(dataset_id, record, update_by)

    @classmethod
    async def append_stage_items(
        cls,
        dataset_id: int,
        items: list[GeneratedDatasetItemVo],
        stage: EvalDatasetStatus,
        update_by: str,
        *,
        finish: bool,
    ) -> int:
        """追加这一阶段的题。最后一阶段写完仍没有题时，记自写题失败。"""
        return await cls._append_stage_items(dataset_id, items, stage, update_by, finish=finish)

    @classmethod
    async def clear_generated_items(cls, dataset_id: int, update_by: str) -> None:
        """圈资料结果丢了、需要重圈时清掉已经写出的题，避免重跑后题目重复。"""
        await cls._clear_generated_items(dataset_id, update_by)

    @classmethod
    async def persist_items(
        cls, dataset_id: int, items: list[GeneratedDatasetItemVo], update_by: str
    ) -> None:
        await cls._persist_items(dataset_id, items, update_by)

    @classmethod
    @transactional()
    async def _mark_status(cls, dataset_id: int, status: str, update_by: str, **extra: Any) -> None:
        values: dict[str, Any] = {
            'dataset_id': dataset_id,
            'status': status,
            'update_by': update_by,
            'update_time': datetime.now(),
            **extra,
        }
        await EvalDatasetDao.update_dataset(values)

    @classmethod
    @transactional()
    async def _touch(cls, dataset_id: int, update_by: str, remark: str | None = None) -> None:
        values: dict[str, Any] = {
            'dataset_id': dataset_id,
            'update_by': update_by,
            'update_time': datetime.now(),
        }
        if remark is not None:
            values['remark'] = remark
        await EvalDatasetDao.update_dataset(values)

    @classmethod
    @transactional()
    async def _save_material(cls, dataset_id: int, record: EvalDatasetMaterialRecordVo, update_by: str) -> None:
        await EvalDatasetDao.update_dataset(
            {
                'dataset_id': dataset_id,
                'status': EvalDatasetStatus.MATERIAL_DONE.value,
                'material_plan': record.model_dump_json(),
                'remark': '',
                'update_by': update_by,
                'update_time': datetime.now(),
            }
        )

    @classmethod
    @transactional()
    async def _append_stage_items(
        cls,
        dataset_id: int,
        items: list[GeneratedDatasetItemVo],
        stage: EvalDatasetStatus,
        update_by: str,
        *,
        finish: bool,
    ) -> int:
        dataset = await EvalDatasetDao.get_dataset_by_id(dataset_id)
        if dataset is None:
            raise ServiceException(message='测评集不存在')
        now = datetime.now()
        start = int(dataset.item_count or 0)
        rows = cls._item_rows(dataset_id, items, update_by, now, start)
        await EvalDatasetDao.insert_items(rows)
        new_count = start + len(rows)
        status = stage.value
        remark = ''
        if finish and new_count == 0:
            status = EvalDatasetStatus.CUSTOM_FAILED.value
            remark = '未生成题目'
        elif finish:
            status = EvalDatasetStatus.READY.value
        await EvalDatasetDao.update_dataset(
            {
                'dataset_id': dataset_id,
                'status': status,
                'item_count': new_count,
                'remark': remark,
                'update_by': update_by,
                'update_time': now,
            }
        )
        return new_count

    @classmethod
    @transactional()
    async def _clear_generated_items(cls, dataset_id: int, update_by: str) -> None:
        now = datetime.now()
        await EvalDatasetDao.soft_delete_items(dataset_id, update_by)
        await EvalDatasetDao.update_dataset(
            {
                'dataset_id': dataset_id,
                'item_count': 0,
                'update_by': update_by,
                'update_time': now,
            }
        )

    @staticmethod
    def _item_rows(
        dataset_id: int,
        items: list[GeneratedDatasetItemVo],
        update_by: str,
        now: datetime,
        start: int,
    ) -> list[KnowledgeEvalDatasetItem]:
        rows: list[KnowledgeEvalDatasetItem] = []
        for offset, it in enumerate(items):
            rows.append(
                KnowledgeEvalDatasetItem(
                    dataset_id=dataset_id,
                    question=it.question,
                    ground_truth=it.ground_truth or '',
                    reference_excerpts=json.dumps(it.reference_excerpts or [], ensure_ascii=False),
                    used_chunk_ids=json.dumps(it.used_chunk_ids or [], ensure_ascii=False),
                    keypoints=json.dumps(it.keypoints or [], ensure_ascii=False),
                    difficulty=(it.difficulty or '')[:64],
                    sort_order=start + offset,
                    enabled=1,
                    create_by=update_by,
                    create_time=now,
                    update_by=update_by,
                    update_time=now,
                    del_flag=DeleteFlag.NORMAL.value,
                )
            )
        return rows

    @classmethod
    @transactional()
    async def _persist_items(
        cls, dataset_id: int, items: list[GeneratedDatasetItemVo], update_by: str
    ) -> None:
        now = datetime.now()
        rows = cls._item_rows(dataset_id, items, update_by, now, 0)
        # 步骤2：作废这套测评集上已有题目，以本次出题结果为准
        await EvalDatasetDao.soft_delete_items(dataset_id, update_by)
        # 步骤3：写入本次题目
        await EvalDatasetDao.insert_items(rows)
        # 步骤4：有题目则测评集可用并记下题目数；没有题目则出题失败
        status = EvalDatasetStatus.READY.value if rows else EvalDatasetStatus.CUSTOM_FAILED.value
        await EvalDatasetDao.update_dataset(
            {
                'dataset_id': dataset_id,
                'status': status,
                'item_count': len(rows),
                'update_by': update_by,
                'update_time': now,
                'remark': '' if rows else '生成结果为空',
            }
        )

    @classmethod
    async def list_datasets(
        cls, query: EvalDatasetPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        return await EvalDatasetDao.get_dataset_list(query, is_page=is_page)

    @classmethod
    async def get_dataset_detail(cls, dataset_id: int) -> EvalDatasetDetailVo:
        dataset = await EvalDatasetDao.get_dataset_by_id(dataset_id)
        if not dataset:
            raise ServiceException(message='测评集不存在')
        items = await EvalDatasetDao.list_items_by_dataset(dataset_id)
        return EvalDatasetDetailVo(
            dataset=EvalDatasetModel(**CamelCaseUtil.transform_result(dataset)),
            items=[EvalDatasetItemModel(**CamelCaseUtil.transform_result(i)) for i in items],
        )

    @classmethod
    async def list_items(
        cls, query: EvalDatasetItemPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        if not query.dataset_id:
            raise ServiceException(message='datasetId 不能为空')
        return await EvalDatasetDao.list_items_by_dataset(
            query.dataset_id, query_object=query, is_page=is_page
        )

    @classmethod
    @transactional()
    async def update_item(
        cls, item_id: int, vo: EvalDatasetItemUpdateVo, current_user: CurrentUserModel
    ) -> CrudResponseModel:
        item = await EvalDatasetDao.get_item_by_id(item_id)
        if not item:
            raise ServiceException(message='题目不存在')
        values: dict[str, Any] = {
            'item_id': item_id,
            'update_by': current_user.user.user_name or '',
            'update_time': datetime.now(),
        }
        if vo.question is not None:
            values['question'] = vo.question
        if vo.ground_truth is not None:
            values['ground_truth'] = vo.ground_truth
        if vo.enabled is not None:
            values['enabled'] = vo.enabled
        await EvalDatasetDao.update_item(values)
        return CrudResponseModel(is_success=True, message='更新成功')
