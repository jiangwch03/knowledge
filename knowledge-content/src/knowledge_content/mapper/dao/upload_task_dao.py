from datetime import datetime

from typing import Any, cast

from sqlalchemy import ColumnElement, func, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.boolean_char_flag_enum import BooleanCharFlag
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.common.vo import PageModel
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.mapper.do.upload_task_do import KnowledgeUploadDocumentParseTask
from knowledge_content.mapper.do.parse_task_do import KnowledgeMineruParseTask
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.vo.upload_task_update_vo import UploadTaskUpdateVO
from knowledge_content.mapper.vo.upload_task_vo import UploadTaskRow
from knowledge_content.vo.document_upload_parse_vo import ListDocumentRecordsQueryModel
from knowledge_common.mapper.dao.base_dao import BaseDao


class KnowledgeUploadTaskDao(BaseDao):
    """
    文档上传任务数据库操作层
    """

    @staticmethod
    async def get_task_by_id(task_id: int) -> KnowledgeUploadDocumentParseTask | None:
        """
        根据任务ID获取上传任务

        :param task_id: 上传任务ID
        :return: 上传任务对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentParseTask).where(
                        KnowledgeUploadDocumentParseTask.task_id == task_id, # type: ignore
                        KnowledgeUploadDocumentParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def get_task_list(
        query_object: ListDocumentRecordsQueryModel,
        is_page: bool = False,
        data_scope_sql: ColumnElement | None = None,
    ) -> PageModel[UploadTaskRow] | list[UploadTaskRow]:
        """
        分页查询上传任务列表

        :param query_object: 查询对象
        :param is_page: 是否分页
        :param data_scope_sql: 数据权限过滤条件
        :return: 上传任务列表
        """
        R = KnowledgeUploadDocumentParseTask
        D = KnowledgeDocument
        # 1. 单表查询上传任务（仅 LEFT JOIN knowledge_document 获取 doc_id），
        #    不与 knowledge_mineru_parse_task 做 JOIN，避免因 1:N 关系导致任务膨胀为重复行
        query = select(
            R.task_id,
            D.doc_id,
            R.doc_title,
            R.doc_desc,
            R.doc_name,
            R.doc_type,
            R.doc_version,
            R.version_remark,
            R.status,
            R.error_code,
            R.error_message,
            R.create_time,
            R.update_time,
        ).outerjoin(
            D,
            (D.task_id == R.task_id)  # type: ignore
            & (D.source_type == DocumentSourceType.UPLOAD.value)
            & (D.del_flag == DeleteFlag.NORMAL.value),  # type: ignore
        ).where(
            R.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        )
        if data_scope_sql is not None:
            query = query.where(data_scope_sql)
        if query_object.doc_title:
            query = query.where(KnowledgeUploadDocumentParseTask.doc_title.like(f'%{query_object.doc_title}%'))
        if query_object.doc_desc:
            query = query.where(KnowledgeUploadDocumentParseTask.doc_desc.like(f'%{query_object.doc_desc}%'))
        if query_object.doc_type:
            query = query.where(KnowledgeUploadDocumentParseTask.doc_type == query_object.doc_type)
        if query_object.status:
            query = query.where(KnowledgeUploadDocumentParseTask.status == query_object.status)
        query = query.order_by(KnowledgeUploadDocumentParseTask.task_id.desc())

        result = await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        # 2. 不管分页与否，提取行列表，统一批量填充 parseTaskId
        rows: list[dict[str, Any]] = cast(PageModel, result).rows if is_page else cast(list, result)
        task_ids = [row.get('taskId') for row in rows if row.get('taskId')]
        if task_ids:
            db = get_current_session()
            T = KnowledgeMineruParseTask
            task_query = (
                select(
                    func.max(T.parse_task_id).label('parse_task_id'),
                    T.task_id,
                )
                .where(
                    T.task_id.in_(task_ids),  # type: ignore
                    T.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .group_by(T.task_id)
            )
            task_rows = (await db.execute(task_query)).all()
            task_map = {row.task_id: row.parse_task_id for row in task_rows}
            for row in rows:
                row['parseTaskId'] = task_map.get(row.get('taskId'))

        return result

    @staticmethod
    async def add_task(task: KnowledgeUploadDocumentParseTask) -> KnowledgeUploadDocumentParseTask:
        """
        新增上传任务

        :param task: 上传任务对象
        :return: 上传任务对象
        """
        db = get_current_session()
        db.add(task)
        await db.flush()
        return task

    @staticmethod
    async def update_status(
        task_id: int,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        clear_errors: bool = False,
        update_by: str = 'admin',
    ) -> None:
        """
        更新上传任务状态

        :param task_id: 上传任务ID
        :param status: 状态
        :param error_code: 错误码
        :param error_message: 错误信息
        :param clear_errors: 是否清空历史错误信息（用于成功状态下覆盖旧错误任务）
        :param update_by: 更新者，默认为 admin（后台任务/消费者专用）
        :return:
        """
        db = get_current_session()
        vo = UploadTaskUpdateVO(status=status, error_code=error_code, error_message=error_message)
        values = vo.to_update_dict(clear_errors=clear_errors)
        values['update_by'] = update_by
        await db.execute(
            update(KnowledgeUploadDocumentParseTask)
            .where(KnowledgeUploadDocumentParseTask.task_id == task_id) # type: ignore
            .values(**values)
        )

    @staticmethod
    async def update_latest_by_title(doc_title: str, exclude_task_id: int | None = None) -> None:
        """
        将同标题其他上传任务的 is_latest 更新为 '0'

        :param doc_title: 文档标题
        :param exclude_task_id: 排除的任务ID
        :return:
        """
        db = get_current_session()
        query = (
            update(KnowledgeUploadDocumentParseTask)
            .where(
                KnowledgeUploadDocumentParseTask.doc_title == doc_title, # type: ignore
                KnowledgeUploadDocumentParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
            )
            .values(is_latest=BooleanCharFlag.NO.value, update_time=datetime.now())
        )
        if exclude_task_id:
            query = query.where(KnowledgeUploadDocumentParseTask.task_id != exclude_task_id)
        await db.execute(query)

    @staticmethod
    async def get_max_version_by_title(doc_title: str) -> str | None:
        """
        获取同标题上传任务最大版本号

        :param doc_title: 文档标题
        :return: 最大版本号
        """
        db = get_current_session()
        result = (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentParseTask.doc_version)
                    .where(
                        KnowledgeUploadDocumentParseTask.doc_title == doc_title, # type: ignore
                        KnowledgeUploadDocumentParseTask.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                    .order_by(KnowledgeUploadDocumentParseTask.doc_version.desc())
                )
            )
            .scalars()
            .first()
        )
        return result

    @staticmethod
    async def get_tasks_by_status(status: str) -> list[KnowledgeUploadDocumentParseTask]:
        """
        按状态查询未删除的上传任务

        :param status: 任务状态
        :return: 上传任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeUploadDocumentParseTask], (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentParseTask).where(
                        KnowledgeUploadDocumentParseTask.status == status, # type: ignore
                        KnowledgeUploadDocumentParseTask.del_flag == DeleteFlag.NORMAL.value, # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def get_tasks_by_statuses(statuses: list[str]) -> list[KnowledgeUploadDocumentParseTask]:
        """
        按多个状态查询未删除的上传任务

        :param statuses: 任务状态列表
        :return: 上传任务列表
        """
        db = get_current_session()
        return cast(list[KnowledgeUploadDocumentParseTask], (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentParseTask).where(
                        KnowledgeUploadDocumentParseTask.status.in_(statuses), # type: ignore
                        KnowledgeUploadDocumentParseTask.del_flag == DeleteFlag.NORMAL.value, # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def soft_delete(task_id: int, update_by: str = '') -> None:
        """
        软删除上传任务

        :param task_id: 上传任务ID
        :param update_by: 更新者
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(KnowledgeUploadDocumentParseTask)
            .where(KnowledgeUploadDocumentParseTask.task_id == task_id) # type: ignore
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
