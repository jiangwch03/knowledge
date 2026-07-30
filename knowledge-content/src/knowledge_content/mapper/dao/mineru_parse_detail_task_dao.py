from datetime import datetime
from typing import cast

from sqlalchemy import select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_content.mapper.do.parse_detail_task_do import KnowledgeMineruParseDetailTask
from knowledge_content.mapper.vo.parse_detail_task_update_vo import MineruParseDetailTaskUpdateVO
from knowledge_common.mapper.dao.base_dao import BaseDao


class KnowledgeMineruParseDetailTaskDao(BaseDao):
    """
    MinerU解析分段任务数据库操作层
    """

    @staticmethod
    async def get_detail_by_id(detail_id: int) -> KnowledgeMineruParseDetailTask | None:
        """
        根据明细ID获取分段任务

        :param detail_id: 明细ID
        :return: 分段任务对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeMineruParseDetailTask).where(
                        KnowledgeMineruParseDetailTask.detail_id == detail_id, # type: ignore
                        KnowledgeMineruParseDetailTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def get_details_by_task_id(
        parse_task_id: int, state: str | None = None
    ) -> list[KnowledgeMineruParseDetailTask]:
        """
        根据解析任务ID获取分段任务列表

        :param parse_task_id: 解析任务ID
        :param state: 状态过滤
        :return: 分段任务列表
        """
        db = get_current_session()
        query = select(KnowledgeMineruParseDetailTask).where(
            KnowledgeMineruParseDetailTask.parse_task_id == parse_task_id, # type: ignore
            KnowledgeMineruParseDetailTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
        )
        if state:
            query = query.where(KnowledgeMineruParseDetailTask.state == state)
        query = query.order_by(KnowledgeMineruParseDetailTask.sequence_number.asc())
        return cast(list[KnowledgeMineruParseDetailTask], (await db.execute(query)).scalars().all())

    @staticmethod
    async def get_details_by_task_ids(
        parse_task_ids: list[int], state: str | None = None
    ) -> list[KnowledgeMineruParseDetailTask]:
        """
        根据解析任务ID列表批量获取分段任务列表

        :param parse_task_ids: 解析任务ID列表
        :param state: 状态过滤
        :return: 分段任务列表
        """
        if not parse_task_ids:
            return []
        db = get_current_session()
        query = select(KnowledgeMineruParseDetailTask).where(
            KnowledgeMineruParseDetailTask.parse_task_id.in_(parse_task_ids),
            KnowledgeMineruParseDetailTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
        )
        if state:
            query = query.where(KnowledgeMineruParseDetailTask.state == state) # type: ignore
        query = query.order_by(KnowledgeMineruParseDetailTask.sequence_number.asc())
        return cast(list[KnowledgeMineruParseDetailTask], (await db.execute(query)).scalars().all())

    @staticmethod
    async def get_details_by_batch_id(batch_id: str) -> list[KnowledgeMineruParseDetailTask]:
        """
        根据批次ID获取分段任务列表

        :param batch_id: 批次ID
        :return: 分段任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeMineruParseDetailTask], (
            (
                await db.execute(
                    select(KnowledgeMineruParseDetailTask).where(
                        KnowledgeMineruParseDetailTask.batch_id == batch_id, # type: ignore
                        KnowledgeMineruParseDetailTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def get_details_by_state(state: str) -> list[KnowledgeMineruParseDetailTask]:
        """
        根据状态获取分段任务列表

        :param state: 状态
        :return: 分段任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeMineruParseDetailTask], (
            (
                await db.execute(
                    select(KnowledgeMineruParseDetailTask).where(
                        KnowledgeMineruParseDetailTask.state == state, # type: ignore
                        KnowledgeMineruParseDetailTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def add_detail(detail: KnowledgeMineruParseDetailTask) -> KnowledgeMineruParseDetailTask:
        """
        新增分段任务

        :param detail: 分段任务对象
        :return: 分段任务对象
        """
        db = get_current_session()
        db.add(detail)
        await db.flush()
        return detail

    @staticmethod
    async def batch_add_details(details: list[KnowledgeMineruParseDetailTask]) -> None:
        """
        批量新增分段任务（一条SQL）

        :param details: 分段任务对象列表
        :return:
        """
        if not details:
            return
        db = get_current_session()
        db.add_all(details)
        await db.flush()

    @staticmethod
    async def update_detail(
        detail_id: int,
        state: str | None = None,
        upload_url: str | None = None,
        upload_expire_at: datetime | None = None,
        batch_id: str | None = None,
        data_id: str | None = None,
        full_zip_url: str | None = None,
        err_msg: str | None = None,
        update_by: str = 'admin',
    ) -> None:
        """
        更新分段任务

        :param detail_id: 分段任务ID
        :param state: 状态
        :param upload_url: 上传链接
        :param upload_expire_at: 链接过期时间
        :param batch_id: 批次ID
        :param data_id: 数据ID
        :param full_zip_url: 结果ZIP链接
        :param err_msg: 错误信息
        :param update_by: 更新者，默认为 admin（后台任务/消费者专用）
        :return:
        """
        db = get_current_session()
        vo = MineruParseDetailTaskUpdateVO(
            state=state, upload_url=upload_url, upload_expire_at=upload_expire_at,
            batch_id=batch_id, data_id=data_id, full_zip_url=full_zip_url, err_msg=err_msg,
        )
        values = vo.to_update_dict()
        if values:
            values['update_by'] = update_by
            await db.execute(
                update(KnowledgeMineruParseDetailTask)
                .where(KnowledgeMineruParseDetailTask.detail_id == detail_id) # type: ignore
                .values(**values)
            )

    @staticmethod
    async def batch_update_state(
        detail_ids: list[int],
        state: str,
        update_by: str = 'admin',
    ) -> None:
        """
        批量更新分段任务状态（根据主键列表，一条SQL）

        :param detail_ids: 主键ID列表
        :param state: 目标状态
        :param update_by: 更新者，默认为 admin（后台任务/消费者专用）
        :return:
        """
        if not detail_ids:
            return
        db = get_current_session()
        await db.execute(
            update(KnowledgeMineruParseDetailTask)
            .where(KnowledgeMineruParseDetailTask.detail_id.in_(detail_ids))
            .values(state=state, update_time=datetime.now(), update_by=update_by)
        )

    @staticmethod
    async def soft_delete_by_task_id(parse_task_id: int, update_by: str = '') -> None:
        """
        根据解析任务ID软删除分段任务

        :param parse_task_id: 解析任务ID
        :param update_by: 更新者
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(KnowledgeMineruParseDetailTask)
            .where(KnowledgeMineruParseDetailTask.parse_task_id == parse_task_id) # type: ignore
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
