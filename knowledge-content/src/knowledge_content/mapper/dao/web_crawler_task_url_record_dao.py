from datetime import datetime

from sqlalchemy import func, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.crawl_url_record_status_enum import CrawlUrlRecordStatus
from knowledge_content.mapper.do.web_crawler_task_url_record_do import WebCrawlerTaskUrlRecord
from knowledge_content.vo.crawl_url_record_upsert_vo import UrlRecordUpsertVo
from knowledge_common.mapper.dao.base_dao import BaseDao


class WebCrawlerTaskUrlRecordDao(BaseDao):
    """
    爬取任务URL记录数据库操作层
    """

    @staticmethod
    async def batch_insert(records: list[WebCrawlerTaskUrlRecord]) -> None:
        """
        批量插入URL记录

        :param records: URL记录列表
        """
        if not records:
            return
        db = get_current_session()
        for record in records:
            db.add(record)
        await db.flush()

    @staticmethod
    async def upsert_by_task_url(vo: UrlRecordUpsertVo) -> None:
        """按 task_id + url 写入：首次插入，重试更新（retry_count+1）"""
        db = get_current_session()
        existing = (
            await db.execute(
                select(WebCrawlerTaskUrlRecord).where(
                    WebCrawlerTaskUrlRecord.task_id == vo.task_id,  # type: ignore
                    WebCrawlerTaskUrlRecord.url == vo.url,  # type: ignore
                    WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            )
        ).scalars().first()
        now = datetime.now()
        if existing is None:
            db.add(
                WebCrawlerTaskUrlRecord(
                    task_id=vo.task_id,
                    url=vo.url,
                    status=vo.status,
                    doc_key=vo.doc_key,
                    title=vo.title or '',
                    status_code=vo.status_code,
                    error_code=vo.error_code,
                    error_message=vo.error_message,
                    retry_count=0,
                    create_by=vo.create_by,
                    update_by=vo.create_by,
                    create_time=now,
                    update_time=now,
                )
            )
            await db.flush()
            return

        existing.status = vo.status
        existing.doc_key = vo.doc_key
        existing.title = vo.title or ''
        existing.status_code = vo.status_code
        existing.error_code = vo.error_code
        existing.error_message = vo.error_message
        existing.retry_count = (existing.retry_count or 0) + 1
        existing.update_by = vo.create_by
        existing.update_time = now
        await db.flush()

    @staticmethod
    async def get_records_by_task_id(
        task_id: int,
        status: str | None = None,
        is_page: bool = True,
        page_num: int = 1,
        page_size: int = 20,
    ) -> PageModel | list[WebCrawlerTaskUrlRecord]:
        """
        按任务ID查询URL记录

        :param task_id: 任务ID
        :param status: 状态过滤
        :param is_page: 是否分页
        :param page_num: 页码
        :param page_size: 每页数量
        :return: 分页或全部记录
        """
        db = get_current_session()
        query = (
            select(WebCrawlerTaskUrlRecord)
            .where(
                WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
        )
        if status:
            query = query.where(WebCrawlerTaskUrlRecord.status == status)  # type: ignore
        query = query.order_by(WebCrawlerTaskUrlRecord.id.asc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page)

    @staticmethod
    async def get_success_urls_by_task_id(task_id: int) -> set[str]:
        """
        查询任务已全链路成功的URL集合

        :param task_id: 任务ID
        :return: 成功URL集合，用于重试时 skip_urls
        """
        db = get_current_session()
        result = await db.execute(
            select(WebCrawlerTaskUrlRecord.url).where(
                WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                WebCrawlerTaskUrlRecord.status == CrawlUrlRecordStatus.SUCCESS.value,  # type: ignore
                WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
        )
        return set(result.scalars().all())

    @staticmethod
    async def get_failed_records_by_task_id(task_id: int) -> list[WebCrawlerTaskUrlRecord]:
        """
        查询任务失败的URL记录

        :param task_id: 任务ID
        :return: 失败URL记录列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTaskUrlRecord).where(
                    WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                    WebCrawlerTaskUrlRecord.status == CrawlUrlRecordStatus.FAILED.value,  # type: ignore
                    WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def get_success_records_with_doc_key(task_id: int) -> list[WebCrawlerTaskUrlRecord]:
        """
        查询任务成功的URL记录（含doc_key），用于合并已爬内容

        :param task_id: 任务ID
        :return: 成功且有doc_key的URL记录列表
        """
        db = get_current_session()
        return list(
            (await db.execute(
                select(WebCrawlerTaskUrlRecord).where(
                    WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                    WebCrawlerTaskUrlRecord.status == CrawlUrlRecordStatus.SUCCESS.value,  # type: ignore
                    WebCrawlerTaskUrlRecord.doc_key.isnot(None),  # type: ignore
                    WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
            ))
            .scalars()
            .all()
        )

    @staticmethod
    async def get_all_records_by_task_id(
        task_id: int,
        status: str | None = None,
    ) -> list[WebCrawlerTaskUrlRecord]:
        """查询任务全部 URL 记录（不分页）"""
        db = get_current_session()
        query = (
            select(WebCrawlerTaskUrlRecord)
            .where(
                WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
        )
        if status:
            query = query.where(WebCrawlerTaskUrlRecord.status == status)  # type: ignore
        query = query.order_by(WebCrawlerTaskUrlRecord.id.asc())  # type: ignore
        return list((await db.execute(query)).scalars().all())

    @staticmethod
    async def get_records_by_urls(task_id: int, urls: list[str]) -> list[WebCrawlerTaskUrlRecord]:
        """按 URL 列表查询记录（用于 rescope 删页）"""
        if not urls:
            return []
        db = get_current_session()
        result = await db.execute(
            select(WebCrawlerTaskUrlRecord).where(
                WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                WebCrawlerTaskUrlRecord.url.in_(urls),  # type: ignore
                WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def soft_delete_by_urls(task_id: int, urls: list[str], update_by: str = '') -> int:
        """按 URL 列表软删记录，返回影响行数"""
        if not urls:
            return 0
        db = get_current_session()
        result = await db.execute(
            update(WebCrawlerTaskUrlRecord)
            .where(
                WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                WebCrawlerTaskUrlRecord.url.in_(urls),  # type: ignore
                WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
        return result.rowcount or 0

    @staticmethod
    async def count_by_status(task_id: int) -> dict[str, int]:
        """统计任务各状态 URL 数量（不含已软删）"""
        db = get_current_session()
        rows = (
            await db.execute(
                select(
                    WebCrawlerTaskUrlRecord.status,  # type: ignore
                    func.count(WebCrawlerTaskUrlRecord.id),  # type: ignore
                )
                .where(
                    WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                    WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
                )
                .group_by(WebCrawlerTaskUrlRecord.status)  # type: ignore
            )
        ).all()
        return {str(status or 'PENDING'): count for status, count in rows}

    @staticmethod
    async def soft_delete_by_task_id(task_id: int, update_by: str = '') -> None:
        """
        软删除任务的所有 URL 记录（未删除的）

        :param task_id: 任务ID
        :param update_by: 更新者
        """
        db = get_current_session()
        await db.execute(
            update(WebCrawlerTaskUrlRecord)
            .where(
                WebCrawlerTaskUrlRecord.task_id == task_id,  # type: ignore
                WebCrawlerTaskUrlRecord.del_flag == DeleteFlag.NORMAL.value,  # type: ignore
            )
            .values(del_flag=DeleteFlag.DELETED.value, update_by=update_by, update_time=datetime.now())
        )
