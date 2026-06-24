from datetime import datetime

from typing import cast

from sqlalchemy import select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_content.enums.mineru_parse_task_status_enum import MineruParseTaskStatus
from knowledge_content.mapper.do.parse_task_do import KnowledgeMineruParseTask
from knowledge_content.mapper.vo.parse_task_update_vo import MineruParseTaskUpdateVO


class KnowledgeMineruParseTaskDao:
    """
    MinerU解析任务数据库操作层
    """

    @staticmethod
    async def get_task_by_id(parse_task_id: int) -> KnowledgeMineruParseTask | None:
        """
        根据解析任务ID获取任务

        :param parse_task_id: 解析任务ID
        :return: 解析任务对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeMineruParseTask).where(
                        KnowledgeMineruParseTask.parse_task_id == parse_task_id, # type: ignore
                        KnowledgeMineruParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def get_active_task_by_record_id(record_id: int) -> KnowledgeMineruParseTask | None:
        """
        根据上传记录ID获取进行中的解析任务

        :param record_id: 上传记录ID
        :return: 解析任务对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeMineruParseTask)
                    .where(
                        KnowledgeMineruParseTask.record_id == record_id, # type: ignore
                        KnowledgeMineruParseTask.status.in_(KnowledgeMineruParseTaskDao.get_active_statuses()),
                        KnowledgeMineruParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                    .order_by(KnowledgeMineruParseTask.create_time.desc())
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def get_tasks_by_record_id_and_status(
        record_id: int, status: str
    ) -> list[KnowledgeMineruParseTask]:
        """
        根据上传记录ID和任务状态获取解析任务列表

        :param record_id: 上传记录ID
        :param status: 任务状态
        :return: 解析任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeMineruParseTask], (
            (
                await db.execute(
                    select(KnowledgeMineruParseTask)
                    .where(
                        KnowledgeMineruParseTask.record_id == record_id, # type: ignore
                        KnowledgeMineruParseTask.status == status, # type: ignore
                        KnowledgeMineruParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                    .order_by(KnowledgeMineruParseTask.create_time.desc())
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def get_tasks_by_record_id(record_id: int) -> list[KnowledgeMineruParseTask]:
        """
        根据上传记录ID获取所有解析任务列表（按创建时间降序）

        :param record_id: 上传记录ID
        :return: 解析任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeMineruParseTask], (
            (
                await db.execute(
                    select(KnowledgeMineruParseTask)
                    .where(
                        KnowledgeMineruParseTask.record_id == record_id,  # type: ignore
                        KnowledgeMineruParseTask.del_flag == DeleteFlag.NORMAL.value  # type: ignore
                    )
                    .order_by(KnowledgeMineruParseTask.create_time.desc())
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def get_tasks_by_status(status: str) -> list[KnowledgeMineruParseTask]:
        """
        根据状态获取解析任务列表

        :param status: 状态
        :return: 解析任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeMineruParseTask], (
            (
                await db.execute(
                    select(KnowledgeMineruParseTask).where(
                        KnowledgeMineruParseTask.status == status, # type: ignore
                        KnowledgeMineruParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def add_task(task: KnowledgeMineruParseTask) -> KnowledgeMineruParseTask:
        """
        新增解析任务

        :param task: 解析任务对象
        :return: 解析任务对象
        """
        db = get_current_session()
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def update_status(
        parse_task_id: int,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        batch_id: str | None = None,
        clear_errors: bool = False,
        update_by: str = 'admin',
    ) -> None:
        """
        更新解析任务状态

        :param parse_task_id: 解析任务ID
        :param status: 状态
        :param error_code: 错误码
        :param error_message: 错误信息
        :param batch_id: 批次ID
        :param clear_errors: 是否清空历史错误信息（用于成功状态下覆盖旧错误记录）
        :param update_by: 更新者，默认为 admin（后台任务/消费者专用）
        :return:
        """
        db = get_current_session()
        vo = MineruParseTaskUpdateVO(status=status, error_code=error_code, error_message=error_message, batch_id=batch_id)
        values = vo.to_update_dict(clear_errors=clear_errors)
        values['update_by'] = update_by
        await db.execute(
            update(KnowledgeMineruParseTask)
            .where(KnowledgeMineruParseTask.parse_task_id == parse_task_id) # type: ignore
            .values(**values)
        )

    @staticmethod
    async def soft_delete_by_record_id(record_id: int, update_by: str = '') -> None:
        """
        根据上传记录ID软删除解析任务

        :param record_id: 上传记录ID
        :param update_by: 更新者
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(KnowledgeMineruParseTask)
            .where(KnowledgeMineruParseTask.record_id == record_id) # type: ignore
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )

    @staticmethod
    def get_active_statuses() -> list[str]:
        """
        获取进行中状态列表

        :return: 进行中状态列表
        """
        return [
            MineruParseTaskStatus.PENDING.value,  # 初始状态：等待调度处理
            MineruParseTaskStatus.LINK_FAILED.value,  # 申请上传链接失败，等待定时任务重试
            MineruParseTaskStatus.WAITING_UPLOAD.value,  # 已获取上传链接，待上传分段文件
            MineruParseTaskStatus.UPLOADING.value,  # 分段上传失败，等待定时任务重试
            MineruParseTaskStatus.PARSING.value,  # MinerU 正在解析中
        ]
