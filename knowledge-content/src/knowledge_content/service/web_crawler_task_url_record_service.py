from knowledge_common.common.vo import PageModel
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_url_record_status_enum import CrawlUrlRecordStatus
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import WebCrawlerTaskUrlRecordDao
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo
from knowledge_content.vo.crawl_url_record_upsert_vo import UrlRecordUpsertVo


class WebCrawlerTaskUrlRecordService:
    """
    爬取任务URL记录服务层
    """

    @classmethod
    async def save_url_records(
        cls,
        task_id: int,
        success_results: list[CrawlProcessedVo],
        failed_results: list[CrawlProcessedVo],
        create_by: str = '',
    ) -> None:
        """
        保存爬取结果URL记录（按 task_id+url 首次新增 / 重试更新）

        :param task_id: 任务ID
        :param success_results: 成功结果列表
        :param failed_results: 失败结果列表
        :param create_by: 创建者
        """
        for result in success_results:
            await WebCrawlerTaskUrlRecordDao.upsert_by_task_url(
                UrlRecordUpsertVo(
                    task_id=task_id,
                    url=result.url,
                    status=CrawlUrlRecordStatus.SUCCESS.value,
                    doc_key=result.object_name,
                    title=result.title or '',
                    status_code=result.status_code,
                    create_by=create_by,
                )
            )

        for result in failed_results:
            await WebCrawlerTaskUrlRecordDao.upsert_by_task_url(
                UrlRecordUpsertVo(
                    task_id=task_id,
                    url=result.url,
                    status=CrawlUrlRecordStatus.FAILED.value,
                    title=result.title or '',
                    error_code=result.error_code,
                    error_message=result.error_message,
                    create_by=create_by,
                )
            )

        if success_results or failed_results:
            logger.info(
                f'[UrlRecord] 保存URL记录: task_id={task_id}, '
                f'success={len(success_results)}, failed={len(failed_results)}',
            )

    @classmethod
    async def get_records_by_task(
        cls,
        task_id: int,
        page_num: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> PageModel:
        """
        获取任务URL记录

        :param task_id: 任务ID
        :param page_num: 页码
        :param page_size: 每页数量
        :param status: 状态过滤
        :return: 分页结果
        """
        return await WebCrawlerTaskUrlRecordDao.get_records_by_task_id(
            task_id=task_id,
            status=status,
            is_page=True,
            page_num=page_num,
            page_size=page_size,
        )
