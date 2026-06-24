from datetime import datetime

from typing import Any, cast

from sqlalchemy import ColumnElement, func, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.common.vo import PageModel
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.mapper.do.upload_record_do import KnowledgeUploadDocumentRecord
from knowledge_content.mapper.do.parse_task_do import KnowledgeMineruParseTask
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.vo.upload_record_update_vo import UploadRecordUpdateVO
from knowledge_content.mapper.vo.upload_record_vo import UploadRecordRow
from knowledge_content.vo.document_upload_parse_vo import ListDocumentRecordsQueryModel


class KnowledgeUploadRecordDao:
    """
    文档上传记录数据库操作层
    """

    @staticmethod
    async def get_record_by_id(record_id: int) -> KnowledgeUploadDocumentRecord | None:
        """
        根据记录ID获取上传记录

        :param record_id: 上传记录ID
        :return: 上传记录对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentRecord).where(
                        KnowledgeUploadDocumentRecord.record_id == record_id, # type: ignore
                        KnowledgeUploadDocumentRecord.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @staticmethod
    async def get_record_list(
        query_object: ListDocumentRecordsQueryModel,
        is_page: bool = False,
        data_scope_sql: ColumnElement | None = None,
    ) -> PageModel[UploadRecordRow] | list[UploadRecordRow]:
        """
        分页查询上传记录列表

        :param query_object: 查询对象
        :param is_page: 是否分页
        :param data_scope_sql: 数据权限过滤条件
        :return: 上传记录列表
        """
        R = KnowledgeUploadDocumentRecord
        D = KnowledgeDocument
        # 1. 单表查询上传记录（仅 LEFT JOIN knowledge_document 获取 doc_id），
        #    不与 knowledge_mineru_parse_task 做 JOIN，避免因 1:N 关系导致记录膨胀为重复行
        query = select(
            R.record_id,
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
            (D.record_id == R.record_id)  # type: ignore
            & (D.del_flag == DeleteFlag.NORMAL.value),  # type: ignore
        ).where(
            R.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
        )
        if data_scope_sql is not None:
            query = query.where(data_scope_sql)
        if query_object.doc_title:
            query = query.where(KnowledgeUploadDocumentRecord.doc_title.like(f'%{query_object.doc_title}%'))
        if query_object.doc_desc:
            query = query.where(KnowledgeUploadDocumentRecord.doc_desc.like(f'%{query_object.doc_desc}%'))
        if query_object.doc_type:
            query = query.where(KnowledgeUploadDocumentRecord.doc_type == query_object.doc_type)
        if query_object.status:
            query = query.where(KnowledgeUploadDocumentRecord.status == query_object.status)
        query = query.order_by(KnowledgeUploadDocumentRecord.record_id.desc())

        result = await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        # 2. 不管分页与否，提取行列表，统一批量填充 parseTaskId
        rows: list[dict[str, Any]] = cast(PageModel, result).rows if is_page else cast(list, result)
        record_ids = [row.get('recordId') for row in rows if row.get('recordId')]
        if record_ids:
            db = get_current_session()
            T = KnowledgeMineruParseTask
            task_query = (
                select(
                    func.max(T.parse_task_id).label('parse_task_id'),
                    T.record_id,
                )
                .where(
                    T.record_id.in_(record_ids),  # type: ignore
                    T.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .group_by(T.record_id)
            )
            task_rows = (await db.execute(task_query)).all()
            task_map = {row.record_id: row.parse_task_id for row in task_rows}
            for row in rows:
                row['parseTaskId'] = task_map.get(row.get('recordId'))

        return result

    @staticmethod
    async def add_record(record: KnowledgeUploadDocumentRecord) -> KnowledgeUploadDocumentRecord:
        """
        新增上传记录

        :param record: 上传记录对象
        :return: 上传记录对象
        """
        db = get_current_session()
        db.add(record)
        await db.flush()
        return record

    @staticmethod
    async def update_status(
        record_id: int,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        clear_errors: bool = False,
        update_by: str = 'admin',
    ) -> None:
        """
        更新上传记录状态

        :param record_id: 上传记录ID
        :param status: 状态
        :param error_code: 错误码
        :param error_message: 错误信息
        :param clear_errors: 是否清空历史错误信息（用于成功状态下覆盖旧错误记录）
        :param update_by: 更新者，默认为 admin（后台任务/消费者专用）
        :return:
        """
        db = get_current_session()
        vo = UploadRecordUpdateVO(status=status, error_code=error_code, error_message=error_message)
        values = vo.to_update_dict(clear_errors=clear_errors)
        values['update_by'] = update_by
        await db.execute(
            update(KnowledgeUploadDocumentRecord)
            .where(KnowledgeUploadDocumentRecord.record_id == record_id) # type: ignore
            .values(**values)
        )

    @staticmethod
    async def update_latest_by_title(doc_title: str, exclude_record_id: int | None = None) -> None:
        """
        将同标题其他上传记录的 is_latest 更新为 '0'

        :param doc_title: 文档标题
        :param exclude_record_id: 排除的记录ID
        :return:
        """
        db = get_current_session()
        query = (
            update(KnowledgeUploadDocumentRecord)
            .where(
                KnowledgeUploadDocumentRecord.doc_title == doc_title, # type: ignore
                KnowledgeUploadDocumentRecord.del_flag == DeleteFlag.NORMAL.value # type: ignore
            )
            .values(is_latest='0', update_time=datetime.now())
        )
        if exclude_record_id:
            query = query.where(KnowledgeUploadDocumentRecord.record_id != exclude_record_id)
        await db.execute(query)

    @staticmethod
    async def get_max_version_by_title(doc_title: str) -> str | None:
        """
        获取同标题上传记录最大版本号

        :param doc_title: 文档标题
        :return: 最大版本号
        """
        db = get_current_session()
        result = (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentRecord.doc_version)
                    .where(
                        KnowledgeUploadDocumentRecord.doc_title == doc_title, # type: ignore
                        KnowledgeUploadDocumentRecord.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                    .order_by(KnowledgeUploadDocumentRecord.doc_version.desc())
                )
            )
            .scalars()
            .first()
        )
        return result

    @staticmethod
    async def get_records_by_status(status: str) -> list[KnowledgeUploadDocumentRecord]:
        """
        按状态查询未删除的上传记录

        :param status: 记录状态
        :return: 上传记录列表
        """
        db = get_current_session()
        return cast(list[KnowledgeUploadDocumentRecord], (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentRecord).where(
                        KnowledgeUploadDocumentRecord.status == status, # type: ignore
                        KnowledgeUploadDocumentRecord.del_flag == DeleteFlag.NORMAL.value, # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def get_records_by_statuses(statuses: list[str]) -> list[KnowledgeUploadDocumentRecord]:
        """
        按多个状态查询未删除的上传记录

        :param statuses: 记录状态列表
        :return: 上传记录列表
        """
        db = get_current_session()
        return cast(list[KnowledgeUploadDocumentRecord], (
            (
                await db.execute(
                    select(KnowledgeUploadDocumentRecord).where(
                        KnowledgeUploadDocumentRecord.status.in_(statuses), # type: ignore
                        KnowledgeUploadDocumentRecord.del_flag == DeleteFlag.NORMAL.value, # type: ignore
                    )
                )
            )
            .scalars()
            .all()
        ))

    @staticmethod
    async def soft_delete(record_id: int, update_by: str = '') -> None:
        """
        软删除上传记录

        :param record_id: 上传记录ID
        :param update_by: 更新者
        :return:
        """
        db = get_current_session()
        await db.execute(
            update(KnowledgeUploadDocumentRecord)
            .where(KnowledgeUploadDocumentRecord.record_id == record_id) # type: ignore
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
