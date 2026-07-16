import tempfile
from pathlib import Path

from sqlalchemy import select

from knowledge_common.common.transactional import async_session_scope
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.config.env import UploadConfig
from knowledge_common.enums.boolean_char_flag_enum import BooleanCharFlag
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.enums.document_status_enum import DocumentStatus
from knowledge_common.enums.document_type_enum import DocumentType
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.page_util import PageUtil
from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.web_crawler_task_dao import WebCrawlerTaskDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.vo.crawl_task_update_vo import CrawlTaskUpdateVo
from knowledge_content.service.document_service import DocumentService
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo


class CrawlerDocumentService:
    """
    爬取文档落库服务层

    负责将爬取结果创建 knowledge_document 记录。
    Markdown 文件已由 CrawlPostProcessorService 上传至 MinIO，本服务只创建文档元数据记录。

    多页爬取时自动合并所有页面的 Markdown 为单个文档（使用 --- 分隔）。
    单页爬取时保持原有行为，直接使用后处理阶段上传的 MinIO 文件。
    """

    @classmethod
    async def persist_documents(cls, task_id: int, target_url: str, results: list[CrawlProcessedVo]) -> None:
        """
    从后处理结果中重建爬取结果并持久化文档

    直接使用后处理阶段返回的成功结果列表，不再经过 URL 记录表。

    :param task_id: 任务ID
    :param target_url: 目标URL
    :param results: 后处理成功的爬取结果列表
    """
        logger.info(f'[CrawlDocConsumer][persist_documents] 开始持久化爬取文档: task_id={task_id}')
        from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService

        try:
            # 步骤1：查询任务状态，非转换失败/爬取完成/转换中的不处理
            task = await WebCrawlerTaskDao.get_task_by_id(task_id)
            if task and task.status not in (
                CrawlTaskStatus.CONVERT_FAILED.value,
                CrawlTaskStatus.COMPLETED.value,
                CrawlTaskStatus.CONVERTING.value,
            ):
                logger.info(f'[CrawlDocConsumer][persist_documents] 任务状态不是CONVERT_FAILED/COMPLETED/CONVERTING，跳过: task_id={task_id}, status={task.status}')
                return

            # 步骤2：查询文档表，如果已存在文档数据则直接退出
            exist_doc = await KnowledgeDocumentDao.get_document_by_task_id(task_id, DocumentSourceType.CRAWL.value)
            if exist_doc:
                logger.info(f'[CrawlDocConsumer][persist_documents] 文档记录已存在，跳过: task_id={task_id}, doc_id={exist_doc.doc_id}')
                return

            if not results:
                logger.info(f'[CrawlDocConsumer][persist_documents] 无成功爬取结果，跳过: task_id={task_id}')
                return

            # CONVERTING 由消费者在开合并前已标记；此处直接落库
            create_by = task.create_by if task else ''
            doc_version = task.doc_version if task else None
            await cls._persist_documents(task_id, target_url, results, create_by, doc_version=doc_version)
        except Exception as e:
            err = format_exception_message(e)
            # 更新任务为 CONVERT_FAILED
            async with async_session_scope() as session:
                task = await WebCrawlerTaskDao.get_task_by_id(task_id)
                update_vo = CrawlTaskUpdateVo(
                    status=CrawlTaskStatus.CONVERT_FAILED.value,
                    error_code=CrawlTaskErrorCode.DOC_PERSIST_ERROR.value,
                    error_message=err,
                    update_by=task.create_by if task else '',
                )
                await WebCrawlerTaskDao.update_task(task_id, update_vo)
                await session.commit()
            logger.exception(
                '[CrawlDocConsumer][persist_documents] 文档持久化失败: task_id={}, error={}',
                task_id, err,
            )
            return

        logger.info(f'[CrawlDocConsumer][persist_documents] 爬取文档持久化完成: task_id={task_id}')
    
    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _persist_documents(
        cls, task_id: int, target_url: str, results: list[CrawlProcessedVo], create_by: str = '',
        doc_version: str | None = None,
    ) -> None:
        """
        将爬取结果持久化为文档记录

        - 单页结果：直接使用后处理阶段已上传的 MinIO 文件创建文档记录
        - 多页结果：下载各页 Markdown 并合并为一个文档后上传落库

        :param task_id: 任务ID
        :param target_url: 目标URL
        :param results: 成功的爬取结果列表
        :param create_by: 创建者标识（取任务表的 create_by）
        """
        from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService

        if len(results) == 1:
            # 单页：直接落库
            await cls._persist_single_document(task_id, target_url, results[0], 0, create_by, doc_version=doc_version)
        else:
            # 多页：合并 Markdown 后落为单个文档
            await cls._persist_merged_document(task_id, target_url, results, create_by, doc_version=doc_version)

        await WebCrawlerTaskService.update_task_status(task_id, CrawlTaskStatus.CONVERTED.value)

    @classmethod
    async def _resolve_doc_version(cls, title: str, doc_version: str | None) -> str:
        """优先使用任务预分配版本号，否则按标题动态生成"""
        if doc_version:
            return doc_version
        return await DocumentService.get_next_version(title)

    @classmethod
    async def _persist_single_document(
        cls, task_id: int, target_url: str, result: CrawlProcessedVo, index: int, create_by: str = '',
        doc_version: str | None = None,
    ) -> None:
        """
        持久化单个爬取结果

        :param task_id: 任务ID
        :param target_url: 目标URL
        :param result: 爬取结果
        :param index: 结果序号
        :param create_by: 创建者标识（取任务表的 create_by）
        """
        title = result.title or result.url
        url = result.url

        # 步骤1：直接使用后处理阶段已上传的 MinIO 对象名（SUCCESS 记录必定有 doc_key）
        doc_key = result.object_name

        # 步骤2：获取版本号（优先任务预分配）
        doc_version = await cls._resolve_doc_version(title, doc_version)

        # 步骤3：创建文档记录
        doc_name = f'{title}.md' if title else f'crawl_result_{task_id}_{index}.md'
        document = KnowledgeDocument(
            task_id=task_id,
            source_type=DocumentSourceType.CRAWL.value,
            doc_title=title,
            doc_name=doc_name,
            doc_type=DocumentType.MD.value,
            source_url=url,
            doc_key=doc_key,
            doc_version=doc_version,
            is_latest=BooleanCharFlag.YES.value,
            status=DocumentStatus.CONVERTED.value,
            user_id=1,  # 后台任务无用户上下文，默认使用 admin 用户
            create_by=create_by,
        )

        result_doc = await KnowledgeDocumentDao.add_document(document)

        # 步骤4：更新同标题旧版本的 is_latest
        await KnowledgeDocumentDao.update_latest_by_title(title, exclude_doc_id=result_doc.doc_id)

        logger.info(f'[Document] 文档落库成功: doc_id={result_doc.doc_id}, title={title}, version={doc_version}')

    @classmethod
    async def _persist_merged_document(
        cls, task_id: int, target_url: str, results: list[CrawlProcessedVo], create_by: str = '',
        doc_version: str | None = None,
    ) -> None:
        """
        将多页爬取结果的 Markdown 合并后落为单个文档

        采用流式写入临时文件策略，避免将所有页面内容同时加载到内存：
        1. 逐页从 MinIO 下载 Markdown → 追加写入临时文件
        2. 从磁盘上传合并文件至 MinIO
        3. 创建单条 knowledge_document 记录

        :param task_id: 任务ID
        :param target_url: 目标URL
        :param results: 成功的爬取结果列表
        :param create_by: 创建者标识（取任务表的 create_by）
        """
        doc_title = results[0].title or target_url

        with tempfile.TemporaryDirectory(dir=UploadConfig.UPLOAD_TEMP_PATH) as tmpdir:
            merge_path = Path(tmpdir) / 'merged_result.md'

            # 1. 逐页下载并合并写入临时文件
            page_count = await cls._merge_pages_to_temp(results, merge_path)

            # 2. 从磁盘上传合并文件到 MinIO
            merged_doc_key = await cls._upload_merged_to_minio(task_id, merge_path)

        # 临时目录已自动清理，3. 创建文档记录
        await cls._create_merged_document(
            task_id, target_url, doc_title, merged_doc_key, page_count, create_by, doc_version=doc_version,
        )

    @classmethod
    async def _merge_pages_to_temp(cls, results: list[CrawlProcessedVo], merge_path: Path) -> int:
        """
        逐页下载 Markdown 并合并写入临时文件

        :param results: 爬取结果列表
        :param merge_path: 合并文件路径
        :return: 成功写入的页数
        """
        page_count = 0
        for i, result in enumerate(results):
            md_content = await KnowledgeMinioService.download_content(result.object_name)
            page_heading = result.title or f'页面 {i + 1}'
            page_section = f'## {page_heading}\n\n来源：{result.url}\n\n{md_content}'

            with open(str(merge_path), 'a', encoding='utf-8') as f:
                if page_count > 0:
                    f.write('\n\n---\n\n')
                f.write(page_section)
            page_count += 1

        return page_count

    @classmethod
    async def _upload_merged_to_minio(cls, task_id: int, merge_path: Path) -> str:
        """
        上传合并后的临时文件到 MinIO

        :param task_id: 任务ID
        :param merge_path: 本地合并文件路径
        :return: MinIO 对象键
        """
        merged_object_name = f'crawler/{task_id}/merged/merged_result.md'
        await KnowledgeMinioService.upload_local_file(str(merge_path), merged_object_name)
        return merged_object_name

    @classmethod
    async def _create_merged_document(
        cls, task_id: int, target_url: str, doc_title: str, merged_doc_key: str, page_count: int,
        create_by: str = '', doc_version: str | None = None,
    ) -> None:
        """创建合并后的文档记录，版本号沿用任务表 doc_version"""
        task = await WebCrawlerTaskDao.get_task_by_id(task_id)
        version = (task.doc_version if task else None) or doc_version
        if not version:
            version = await DocumentService.get_next_version(target_url)

        document = KnowledgeDocument(
            task_id=task_id,
            source_type=DocumentSourceType.CRAWL.value,
            doc_title=doc_title,
            doc_name=f'{doc_title}.md',
            doc_type=DocumentType.MD.value,
            source_url=target_url,
            doc_key=merged_doc_key,
            doc_version=version,
            is_latest=BooleanCharFlag.YES.value,
            status=DocumentStatus.CONVERTED.value,
            user_id=1,
            create_by=create_by,
        )
        result_doc = await KnowledgeDocumentDao.add_document(document)
        await KnowledgeDocumentDao.update_latest_by_title(doc_title, exclude_doc_id=result_doc.doc_id)

        logger.info(
            f'[Document] 多页合并文档落库成功: doc_id={result_doc.doc_id}, '
            f'title={doc_title}, version={version}, pages={page_count}',
        )

    @classmethod
    async def get_documents_by_task(
        cls,
        task_id: int | None = None,
        page_num: int = 1,
        page_size: int = 20,
        status: str | None = None,
        create_by: str | None = None,
        del_flag: str | None = None,
    ) -> PageModel:
        """
        获取任务关联的文档列表

        :param task_id: 任务ID（为空时查询全部爬取文档）
        :param page_num: 页码
        :param page_size: 每页数量
        :param status: 文档状态过滤
        :param create_by: 操作用户模糊搜索
        :param del_flag: 删除标识过滤
        :return: 分页结果
        """
        query = (
            select(KnowledgeDocument)
            .where(
                KnowledgeDocument.source_type == DocumentSourceType.CRAWL.value,
            )
        )
        # 删除标识过滤：默认只查未删除，指定 del_flag 时按查询值过滤
        if del_flag is not None:
            query = query.where(KnowledgeDocument.del_flag == del_flag)  # type: ignore
        else:
            query = query.where(KnowledgeDocument.del_flag == DeleteFlag.NORMAL.value)  # type: ignore

        if task_id is not None:
            query = query.where(KnowledgeDocument.task_id == task_id)  # type: ignore
        if status is not None:
            query = query.where(KnowledgeDocument.status == status)  # type: ignore
        if create_by is not None:
            query = query.where(KnowledgeDocument.create_by.like(f'%{create_by}%'))  # type: ignore
        query = query.order_by(KnowledgeDocument.doc_id.desc())  # type: ignore
        return await PageUtil.paginate(query, page_num, page_size, is_page=True)
