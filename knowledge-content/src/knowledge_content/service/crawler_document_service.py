import tempfile
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

from knowledge_common.common import get_current_session
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.config.env import UploadConfig
from knowledge_common.enums.boolean_char_flag_enum import BooleanCharFlag
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.enums.document_type_enum import DocumentType
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_file_dao import KnowledgeDocumentFileDao
from knowledge_content.mapper.dao.web_crawler_task_dao import WebCrawlerTaskDao
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import WebCrawlerTaskUrlRecordDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_file_do import KnowledgeDocumentFile
from knowledge_content.mapper.do.web_crawler_task_do import WebCrawlerTask
from knowledge_content.mapper.vo.crawl_task_update_vo import CrawlTaskUpdateVo
from knowledge_content.service.document_service import DocumentService
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


class CrawlerDocumentService:
    """
    爬取文档落库服务层

    负责将爬取结果创建 knowledge_document + knowledge_document_file。
    Markdown 已由 CrawlPostProcessorService 上传至 MinIO；本服务写主表元数据与子表文件行。

    默认路径：1 主表 + N 子表（不合并多页）。
    合并实现保留在 _merge_* / _persist_merged_document，供日后迁回，默认不调用。
    """

    @classmethod
    async def persist_documents(cls, task_id: int) -> None:
        """
        从成功爬取结果持久化文档（主表 + 文件子表）

        :param task_id: 任务ID
        :param target_url: 目标URL
        """
        logger.info(f'[CrawlDocConsumer][persist_documents] 开始持久化爬取文档: task_id={task_id}')
        task = await WebCrawlerTaskDao.get_task_by_id(task_id)
        if not task:
            logger.warning(f'[CrawlDocConsumer] 任务不存在，跳过: task_id={task_id}')
            return

        if task.status not in (
                CrawlTaskStatus.CONVERT_FAILED.value,
                CrawlTaskStatus.COMPLETED.value
        ):
            logger.info(
                f'[CrawlDocConsumer][persist_documents] 任务状态不是CONVERT_FAILED/COMPLETED，跳过: '
                f'task_id={task_id}, status={task.status}'
            )
            return

        exist_doc = await KnowledgeDocumentDao.get_document_by_task_id(task_id, DocumentSourceType.CRAWL.value)
        if exist_doc:
            logger.info(
                f'[CrawlDocConsumer][persist_documents] 文档记录已存在，跳过: task_id={task_id}, doc_id={exist_doc.doc_id}'
            )
            return

        try:
            success_records = await WebCrawlerTaskUrlRecordDao.get_success_records_with_doc_key(task_id)
            if not success_records or len(success_records) == 0:
                logger.info(f'[CrawlDocConsumer][persist_documents] 无成功爬取结果，跳过: task_id={task_id}')
                return

            results = [
                CrawlProcessedVo(
                    success=True,
                    url=record.url,
                    title=record.title or '',
                    object_name=record.doc_key,
                )
                for record in success_records
            ]

            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.CONVERTING.value,
            )
            logger.info(f'[CrawlDocConsumer] 已标记落库中: task_id={task_id}')

            await cls._persist_documents(task, results)
            logger.info(f'[CrawlDocConsumer][persist_documents] 爬取文档持久化完成: task_id={task_id}')
        except Exception as e:
            err = format_exception_message(e)
            session = get_current_session()
            task = await WebCrawlerTaskDao.get_task_by_id(task_id)
            update_vo = CrawlTaskUpdateVo(
                status=CrawlTaskStatus.CONVERT_FAILED.value,
                error_code=CrawlTaskErrorCode.DOC_PERSIST_ERROR.value,
                error_message=err,
                update_by=task.create_by if task else 'admin',
            )
            await WebCrawlerTaskDao.update_task(task_id, update_vo)
            await session.commit()
            logger.exception(
                '[CrawlDocConsumer][persist_documents] 文档持久化失败: task_id={}, error={}',
                task_id,
                err,
            )
            return



    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _persist_documents(
        cls,
        task: WebCrawlerTask,
        results: list[CrawlProcessedVo],
    ) -> None:
        """统一落库：1 条 knowledge_document + N 条 knowledge_document_file（不合并）"""
        task_id = task.task_id
        target_url = task.target_url
        create_by = task.create_by if task else 'admin'
        doc_title = target_url
        version = await cls._resolve_doc_version(doc_title, task.doc_version)

        document = KnowledgeDocument(
            task_id=task_id,
            source_type=DocumentSourceType.CRAWL.value,
            doc_title=doc_title,
            doc_desc=doc_title + "爬取",
            doc_version=version,
            is_latest=BooleanCharFlag.YES.value,
            version_remark=version,
            user_id=task.user_id,
            dept_id=task.dept_id,
            create_by=create_by,
            update_by=create_by,
        )
        result_doc = await KnowledgeDocumentDao.add_document(document)
        await KnowledgeDocumentDao.update_latest_by_title(doc_title, exclude_doc_id=result_doc.doc_id)

        file_rows: list[KnowledgeDocumentFile] = []
        for i, result in enumerate(results):
            title = result.title or result.url or f'page_{i + 1}'
            doc_name = cls._build_page_doc_name(title, result.url, task_id, i)
            file_rows.append(
                KnowledgeDocumentFile(
                    doc_id=result_doc.doc_id,
                    task_id=task_id,
                    doc_name=doc_name,
                    doc_type=DocumentType.MD.value,
                    source_url=result.url,
                    original_doc_key=result.object_name,
                    doc_key=result.object_name,
                    create_by=create_by,
                    update_by=create_by,
                )
            )
        await KnowledgeDocumentFileDao.add_files(file_rows)

        await WebCrawlerTaskService.update_task_status(task_id, CrawlTaskStatus.CONVERTED.value)
        logger.info(
            f'[Document] 爬取文档落库成功: doc_id={result_doc.doc_id}, title={doc_title}, '
            f'version={version}, files={len(file_rows)}'
        )

    @classmethod
    def _build_page_doc_name(cls, title: str, url: str | None, task_id: int, index: int) -> str:
        name = (title or '').strip()
        if name:
            if not name.lower().endswith('.md'):
                name = f'{name}.md'
            return name
        if url:
            path = urlparse(url).path.rstrip('/')
            base = path.split('/')[-1] if path else ''
            if base:
                return base if base.lower().endswith('.md') else f'{base}.md'
        return f'crawl_result_{task_id}_{index}.md'

    @classmethod
    async def _resolve_doc_version(cls, title: str, doc_version: str | None) -> str:
        if doc_version:
            return doc_version
        return await DocumentService.get_next_version(title)

    # ------------------------------------------------------------------
    # 以下为「多页合并落库」实现，默认路径不调用；保留供日后迁回复用
    # ------------------------------------------------------------------

    @classmethod
    async def _persist_merged_document(
        cls,
        task_id: int,
        target_url: str,
        results: list[CrawlProcessedVo],
        create_by: str = '',
        doc_version: str | None = None,
    ) -> None:
        """
        【迁回用 / 默认不调用】将多页 Markdown 合并后落为单个文档+单文件行
        """
        doc_title = results[0].title or target_url

        with tempfile.TemporaryDirectory(dir=UploadConfig.UPLOAD_TEMP_PATH) as tmpdir:
            merge_path = Path(tmpdir) / 'merged_result.md'
            page_count = await cls._merge_pages_to_temp(results, merge_path)
            merged_doc_key = await cls._upload_merged_to_minio(task_id, merge_path)

        await cls._create_merged_document(
            task_id,
            target_url,
            doc_title,
            merged_doc_key,
            page_count,
            create_by,
            doc_version=doc_version,
        )

    @classmethod
    async def _merge_pages_to_temp(cls, results: list[CrawlProcessedVo], merge_path: Path) -> int:
        """【迁回用】逐页下载 Markdown 并合并写入临时文件"""
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
        """【迁回用】上传合并后的临时文件到 MinIO"""
        merged_object_name = f'crawler/{task_id}/merged/merged_result.md'
        await KnowledgeMinioService.upload_local_file(str(merge_path), merged_object_name)
        return merged_object_name

    @classmethod
    async def _create_merged_document(
        cls,
        task_id: int,
        target_url: str,
        doc_title: str,
        merged_doc_key: str,
        page_count: int,
        create_by: str = '',
        doc_version: str | None = None,
    ) -> None:
        """【迁回用】创建合并后的文档主表 + 单文件子表行"""
        task = await WebCrawlerTaskDao.get_task_by_id(task_id)
        version = (task.doc_version if task else None) or doc_version
        if not version:
            version = await DocumentService.get_next_version(target_url)

        document = KnowledgeDocument(
            task_id=task_id,
            source_type=DocumentSourceType.CRAWL.value,
            doc_title=doc_title,
            doc_version=version,
            is_latest=BooleanCharFlag.YES.value,
            user_id=1,
            create_by=create_by,
        )
        result_doc = await KnowledgeDocumentDao.add_document(document)
        await KnowledgeDocumentDao.update_latest_by_title(doc_title, exclude_doc_id=result_doc.doc_id)
        await KnowledgeDocumentFileDao.add_file(
            KnowledgeDocumentFile(
                doc_id=result_doc.doc_id,
                task_id=task_id,
                doc_name=f'{doc_title}.md',
                doc_type=DocumentType.MD.value,
                source_url=target_url,
                original_doc_key=None,
                doc_key=merged_doc_key,
                create_by=create_by,
            )
        )

        logger.info(
            f'[Document] 多页合并文档落库成功(迁回路径): doc_id={result_doc.doc_id}, '
            f'title={doc_title}, version={version}, pages={page_count}',
        )

    @classmethod
    async def get_documents_by_task(
        cls,
        task_id: int | None = None,
        page_num: int = 1,
        page_size: int = 20,
        doc_title: str | None = None,
        create_by: str | None = None,
        del_flag: str | None = None,
    ) -> PageModel:
        """获取任务关联的文档列表（主表分页 + 子表摘要）"""
        page = await KnowledgeDocumentDao.get_crawl_document_list(
            task_id=task_id,
            doc_title=doc_title,
            create_by=create_by,
            del_flag=del_flag,
            page_num=page_num,
            page_size=page_size,
        )
        # PageUtil 经 CamelCaseUtil 后 rows 已是 camelCase dict；批量查子表装配摘要
        rows = page.rows or []
        doc_ids = [doc.get('docId') for doc in rows if doc.get('docId') is not None]
        files = await KnowledgeDocumentFileDao.list_by_doc_ids(doc_ids)
        files_by_doc: dict[int, list] = defaultdict(list)
        for f in files:
            files_by_doc[f.doc_id].append(f)
        for doc in rows:
            doc_files = files_by_doc.get(doc.get('docId'), [])
            doc['fileCount'] = len(doc_files)
            first = doc_files[0] if doc_files else None
            doc['docName'] = first.doc_name if first else None
            doc['docType'] = first.doc_type if first else None
            doc['sourceUrl'] = first.source_url if first else None
        return page
