from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.do.job_do import SysJob
from knowledge_common.vo.job_vo import JobModel, JobPageQueryModel
from knowledge_common.utils.page_util import PageUtil


class JobDao:
    """
    定时任务管理模块数据库操作层
    """

    @classmethod
    async def get_job_detail_by_id(cls, job_id: int) -> SysJob | None:
        """
        根据定时任务id获取定时任务详细信息

        :param job_id: 定时任务id
        :return: 定时任务信息对象
        """
        db = get_current_session()
        job_info = (await db.execute(select(SysJob).where(SysJob.job_id == job_id))).scalars().first()

        return job_info

    @classmethod
    async def get_job_detail_by_info(cls, job: JobModel) -> SysJob | None:
        """
        根据定时任务参数获取定时任务信息

        :param job: 定时任务参数对象
        :return: 定时任务信息对象
        """
        db = get_current_session()
        job_info = (
            (
                await db.execute(
                    select(SysJob).where(
                        SysJob.job_name == job.job_name,
                        SysJob.job_group == job.job_group,
                        SysJob.job_executor == job.job_executor,
                        SysJob.invoke_target == job.invoke_target,
                        SysJob.job_args == job.job_args,
                        SysJob.job_kwargs == job.job_kwargs,
                        SysJob.cron_expression == job.cron_expression,
                    )
                )
            )
            .scalars()
            .first()
        )

        return job_info

    @classmethod
    async def get_job_list(
        cls, query_object: JobPageQueryModel, is_page: bool = False
    ) -> PageModel | list[dict[str, Any]]:
        """
        根据查询参数获取定时任务列表信息

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 定时任务列表信息对象
        """
        db = get_current_session()
        query = (
            select(SysJob)
            .where(
                SysJob.job_name.like(f'%{query_object.job_name}%') if query_object.job_name else True,
                SysJob.job_group == query_object.job_group if query_object.job_group else True,
                SysJob.status == query_object.status if query_object.status else True,
                SysJob.app_scope == query_object.app_scope if query_object.app_scope else True,
            )
            .order_by(SysJob.job_id)
            .distinct()
        )
        job_list: PageModel | list[dict[str, Any]] = await PageUtil.paginate(
            query, query_object.page_num, query_object.page_size, is_page
        )

        return job_list

    @classmethod
    async def get_job_list_for_scheduler(cls, app_scope: str | None = None) -> Sequence[SysJob]:
        """
        获取定时任务列表信息

        :param app_scope: 应用标识，为None时加载status='0'的全部任务
        :return: 定时任务列表信息对象
        """
        db = get_current_session()
        query = select(SysJob).where(SysJob.status == '0')
        if app_scope:
            query = query.where(
                (SysJob.app_scope == app_scope) | (SysJob.app_scope.is_(None)) | (SysJob.app_scope == '')
            )
        job_list = (await db.execute(query.distinct())).scalars().all()

        return job_list

    @classmethod
    async def get_all_job_list_for_scheduler(cls, app_scope: str | None = None) -> Sequence[SysJob]:
        """
        获取全部定时任务列表信息

        :param app_scope: 应用标识
        :return: 定时任务列表信息对象
        """
        db = get_current_session()
        query = select(SysJob)
        if app_scope:
            query = query.where(
                (SysJob.app_scope == app_scope) | (SysJob.app_scope.is_(None)) | (SysJob.app_scope == '')
            )
        job_list = (await db.execute(query.distinct())).scalars().all()

        return job_list

    @classmethod
    async def add_job_dao(cls, job: JobModel) -> SysJob:
        """
        新增定时任务数据库操作

        :param job: 定时任务对象
        :return:
        """
        db = get_current_session()
        db_job = SysJob(**job.model_dump())
        db.add(db_job)
        await db.flush()

        return db_job

    @classmethod
    async def edit_job_dao(cls, job: dict, old_job: JobModel) -> None:
        """
        编辑定时任务数据库操作

        :param job: 需要更新的定时任务字典
        :param old_job: 原定时任务对象
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(SysJob)
            .where(
                SysJob.job_id == old_job.job_id,
                SysJob.job_name == old_job.job_name,
                SysJob.job_group == old_job.job_group,
            )
            .values(**job)
        )

    @classmethod
    async def delete_job_dao(cls, job: JobModel) -> None:
        """
        删除定时任务数据库操作

        :param job: 定时任务对象
        :return:
        """
        db = get_current_session()
        await db.execute(delete(SysJob).where(SysJob.job_id.in_([job.job_id])))
