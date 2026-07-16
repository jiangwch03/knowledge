from datetime import datetime

from sqlalchemy import ColumnElement, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.do.web_crawler_task_do import WebCrawlerTask
from knowledge_content.mapper.vo.crawl_task_update_vo import CrawlTaskUpdateVo


class WebCrawlerTaskDao:
    """
    爬取任务数据库操作层
    """

    @staticmethod
    async def get_task_by_id(task_id: int) -> WebCrawlerTask | None:
        """
        根据任务ID获取任务

        :param task_id: 任务ID
        :return: 任务对象
        """
        db = get_current_session()
        return (
            (await db.execute(select(WebCrawlerTask).where(
                WebCrawlerTask.task_id == task_id,  # type: ignore
                WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )))
            .scalars()
            .first()
        )

    @staticmethod
    async def get_task_by_id_with_scope(
        task_id: int,
        data_scope_sql: ColumnElement,
    ) -> WebCrawlerTask | None:
        """
        根据任务ID获取任务，并校验数据权限

        :param task_id: 任务ID
        :param data_scope_sql: 数据权限过滤条件
        :return: 有权限时返回任务，否则 None
        """
        db = get_current_session()
        return (
            (await db.execute(select(WebCrawlerTask).where(
                WebCrawlerTask.task_id == task_id,  # type: ignore
                WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                data_scope_sql,
            )))
            .scalars()
            .first()
        )

    @staticmethod
    async def get_task_list(
        user_id: int | None = None,
        status: str | None = None,
        statuses: list[str] | None = None,
        create_by: str | None = None,
        is_page: bool = False,
        page_num: int = 1,
        page_size: int = 20,
        data_scope_sql: ColumnElement | None = None,
    ) -> PageModel | list[WebCrawlerTask]:
        """
        分页查询任务列表

        :param user_id: 用户ID
        :param status: 单状态过滤
        :param statuses: 多状态过滤（优先于 status）
        :param create_by: 操作用户模糊搜索
        :param is_page: 是否分页
        :param page_num: 页码
        :param page_size: 每页数量
        :param data_scope_sql: 数据权限过滤条件
        :return: 任务列表
        """
        query = select(WebCrawlerTask).where(
            WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        )
        if data_scope_sql is not None:
            query = query.where(data_scope_sql)
        elif user_id is not None:
            query = query.where(WebCrawlerTask.user_id == user_id)  # type: ignore
        if statuses:
            query = query.where(WebCrawlerTask.status.in_(statuses))  # type: ignore
        elif status:
            query = query.where(WebCrawlerTask.status == status)  # type: ignore
        if create_by:
            query = query.where(WebCrawlerTask.create_by.like(f'%{create_by}%'))  # type: ignore
        query = query.order_by(WebCrawlerTask.task_id.desc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page)

    @staticmethod
    async def get_latest_task_by_url_with_scope(
        target_url: str,
        data_scope_sql: ColumnElement,
    ) -> WebCrawlerTask | None:
        """
        按目标 URL 查询最新版本的爬取任务（数据权限过滤）

        优先按 doc_version 主版本号降序，相同版本按 task_id 降序。
        """
        from sqlalchemy import Integer, cast, func

        db = get_current_session()
        version_major = cast(
            func.substring_index(func.coalesce(WebCrawlerTask.doc_version, '0.0'), '.', 1),
            Integer,
        )
        return (
            (await db.execute(
                select(WebCrawlerTask).where(
                    WebCrawlerTask.target_url == target_url,  # type: ignore
                    WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                    data_scope_sql,
                ).order_by(
                    version_major.desc(),
                    WebCrawlerTask.task_id.desc(),  # type: ignore
                ).limit(1)
            ))
            .scalars()
            .first()
        )

    @staticmethod
    async def add_task(task: WebCrawlerTask) -> WebCrawlerTask:
        """
        新增任务

        :param task: 任务对象
        :return: 任务对象
        """
        db = get_current_session()
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def update_task(task_id: int, vo: CrawlTaskUpdateVo) -> None:
        """
        更新任务（合并原 update_task / update_status / update_progress）

        所有字段均通过 CrawlTaskUpdateVo 传入，
        update_by / clear_errors 等控制字段也由 VO 承载。

        :param task_id: 任务ID
        :param vo: 更新值对象
        :return:
        """
        db = get_current_session()
        values = vo.to_update_dict()
        values['update_time'] = datetime.now()
        await db.execute(
            update(WebCrawlerTask)
            .where(WebCrawlerTask.task_id == task_id)  # type: ignore
            .values(**values)
        )

    @staticmethod
    async def get_tasks_by_status(status: str) -> list[WebCrawlerTask]:
        """
        按状态查询未删除的任务

        :param status: 任务状态
        :return: 任务列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTask).where(
                    WebCrawlerTask.status == status,  # type: ignore
                    WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def get_tasks_by_statuses(statuses: list[str]) -> list[WebCrawlerTask]:
        """
        按多个状态查询未删除的任务

        :param statuses: 任务状态列表
        :return: 任务列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTask).where(
                    WebCrawlerTask.status.in_(statuses),  # type: ignore
                    WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def get_tasks_by_status_and_time_before(
        status: str,
        time_before: datetime,
    ) -> list[WebCrawlerTask]:
        """
        按状态查询指定时间之前开始的未删除任务（用于 RUNNING 超时兜底）

        :param status: 任务状态
        :param time_before: 截止时间
        :return: 任务列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTask).where(
                    WebCrawlerTask.status == status,  # type: ignore
                    WebCrawlerTask.started_time < time_before,  # type: ignore
                    WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def get_zombie_running_tasks(update_before: datetime) -> list[WebCrawlerTask]:
        """
        查询进度停更的 RUNNING 任务（僵尸检测候选）

        :param update_before: update_time 截止点
        :return: 任务列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTask).where(
                    WebCrawlerTask.status == CrawlTaskStatus.RUNNING.value,  # type: ignore
                    WebCrawlerTask.update_time < update_before,  # type: ignore
                    WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def get_pending_tasks_created_before(time_before: datetime) -> list[WebCrawlerTask]:
        """
        查询指定时间之前创建、仍处于 PENDING 的未删除任务（用于消息丢失兜底）

        :param time_before: 创建时间截止点
        :return: 任务列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTask).where(
                    WebCrawlerTask.status == CrawlTaskStatus.PENDING.value,  # type: ignore
                    WebCrawlerTask.create_time < time_before,  # type: ignore
                    WebCrawlerTask.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def soft_delete(task_id: int, update_by: str = '') -> None:
        """
        软删除任务

        :param task_id: 任务ID
        :param update_by: 更新者
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(WebCrawlerTask)
            .where(WebCrawlerTask.task_id == task_id)  # type: ignore
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
