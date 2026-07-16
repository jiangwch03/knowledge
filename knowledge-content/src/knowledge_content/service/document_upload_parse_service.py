from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import ColumnElement

from fastapi import UploadFile
from knowledge_common.common.context import RequestContext
from knowledge_common.common.transactional import get_current_session, transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.enums.boolean_char_flag_enum import BooleanCharFlag
from knowledge_common.enums.document_status_enum import DocumentStatus
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.file_util import FileUtil
from knowledge_common.config.env import MinioConfig, UploadConfig, StreamTopicConfig
from knowledge_common.utils.log_util import logger

from knowledge_content.enums.document_upload_status_enum import DocumentUploadStatus
from knowledge_content.enums.mineru_parse_detail_state_enum import MineruParseDetailState
from knowledge_content.enums.mineru_enum import (
    FormulaSwitch,
    MinerUParseModeEnum,
    OcrSwitch,
    TableSwitch,
)
from knowledge_content.enums.parse_decision_action_enum import ParseDecisionAction
from knowledge_content.enums.mineru_parse_task_status_enum import MineruParseTaskStatus
from knowledge_content.infra.mineru.mineru_client import MineUClient
from knowledge_content.infra.mineru.vo.mineru_batch_upload_vo import (
    MinerUBatchUploadReqVo,
    MinerUFileItem, MinerUApplyUploadUrlsVo,
)
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.mineru_parse_detail_task_dao import (
    KnowledgeMineruParseDetailTaskDao,
)
from knowledge_content.mapper.dao.mineru_parse_task_dao import KnowledgeMineruParseTaskDao
from knowledge_content.mapper.dao.upload_task_dao import KnowledgeUploadTaskDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.parse_detail_task_do import KnowledgeMineruParseDetailTask
from knowledge_content.mapper.do.parse_task_do import KnowledgeMineruParseTask
from knowledge_content.mapper.do.upload_task_do import KnowledgeUploadDocumentParseTask
from knowledge_content.service.mineru_zip_merge_service import MineruZipMergeService
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.service.vo.message_stream_topic_vo import DocumentParsePending, DocumentMdPending
from knowledge_content.vo.document_upload_parse_vo import (
    GetParseTaskDetailsResponseModel,
    GetParseTaskResponseModel,
    HandleParseDecisionModel,
    ListDocumentRecordsQueryModel,
    ListDocumentRecordsResponseModel,
    ParseTaskItemResponseModel,
    UploadDocumentModel,
    UploadDocumentResponseModel,
)
from knowledge_content.service.vo.mineru_zip_merge_vo import MineruZipSegmentVo
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.redis import DistributedLock, LockKey


class DocumentUploadParseService:
    """
    文档上传与 MinerU 解析服务层

    负责上传记录、解析任务、解析分段全生命周期管理，
    与 knowledge_document 文件主表解耦。
    """

    SUPPORTED_TYPES = {'pdf', 'doc', 'docx', 'xlsx', 'md'}
    PARSE_TYPES = {'pdf', 'doc', 'docx', 'xlsx'}
    TXT_MAX_BYTES = 512 * 1024
    MAX_PAGES_PER_SEGMENT = 300
    UPLOAD_EXPIRE_HOURS = 23
    UPLOAD_EXPIRE_MINUTES = 50

    # region 上传任务入口

    @classmethod
    def _get_file_extension(cls, filename: str) -> str:
        """获取文件后缀（小写）"""
        return Path(filename).suffix.lstrip('.').lower()

    @classmethod
    def _is_supported(cls, ext: str) -> bool:
        """是否支持该文件类型"""
        return ext in cls.SUPPORTED_TYPES

    @classmethod
    def _resolve_next_version(cls, current_max: str | None) -> str:
        """根据当前最大版本号递增生成新版本号"""
        if not current_max:
            return '1.0'
        try:
            major = int(float(current_max))
            return f'{major + 1}.0'
        except ValueError:
            return '1.0'

    @classmethod
    async def get_next_version(cls, doc_title: str) -> str:
        """
        根据文档标题查询最新版本号并返回下一版本（查不到返回 1.0）

        :param doc_title: 文档标题
        :return: 下一版本号，如 '2.0'
        """
        max_version = await KnowledgeUploadTaskDao.get_max_version_by_title(doc_title)
        return cls._resolve_next_version(max_version)

    @classmethod
    async def upload_document(
            cls,
            file: UploadFile,
            upload_model: UploadDocumentModel,
    ) -> UploadDocumentResponseModel:
        """
        文档上传入口

        :param file: 上传文件
        :param upload_model: 上传参数（含自动注入的 userInfo）
        :return: 上传任务
        """
        filename = file.filename
        if not filename:
            raise ServiceException('文件名为空')
        # 获取文件后缀
        ext = cls._get_file_extension(filename)
        if not cls._is_supported(ext):
            raise ServiceException(f'不支持的文件类型: {ext}')

        # 分布式锁：基于文件名防止短时重复上传（网络抖动引起重复请求）
        lock_key = LockKey.upload_document_key(filename)
        async with DistributedLock(lock_key, expire=30, timeout=0, renew=True) as acquired:
            if not acquired:
                raise ServiceException('该文件正在上传中，请稍后重试')

            response, parse_task_id = await cls._upload_document(file, upload_model, ext)

        # 事务提交后再发消息，避免消费者读不到未提交的解析任务
        if parse_task_id is not None:
            await cls._publish_parse_pending(parse_task_id)
        return response

    @classmethod
    @transactional()
    async def _upload_document(
            cls,
            file: UploadFile,
            upload_model: UploadDocumentModel, ext: str
    ) -> tuple[UploadDocumentResponseModel, int | None]:
        """
        文档上传落库（私有）

        :return: (上传响应, 需发消息的 parse_task_id；MD 直落库则为 None)
        """
        user_id = upload_model.userInfo.user.user_id
        dept_id = upload_model.userInfo.user.dept_id
        user_name = upload_model.userInfo.user.user_name
        filename = file.filename

        # 将上传文件写入本地临时文件（分块读取，避免大文件全部加载到内存）
        temp_file = await FileUtil.save_upload_to_temp(
            file,
            max_size=UploadConfig.UPLOAD_MAX_SIZE,
            temp_dir=UploadConfig.UPLOAD_TEMP_PATH,
        )
        temp_path = temp_file.path

        try:
            # 上传原始文件到 MinIO（从本地文件上传，无需加载到内存）
            object_name = f'{MinioConfig.minio_object_document_prefix}/{datetime.now().strftime("%Y%m%d")}/{user_id}_{datetime.now().timestamp()}_{filename}'
            await KnowledgeMinioService.upload_local_file(temp_path, object_name)
            original_doc_key = object_name

            # 版本预占
            doc_title = upload_model.doc_title or filename
            max_version = await KnowledgeUploadTaskDao.get_max_version_by_title(doc_title)
            next_version = cls._resolve_next_version(max_version)
            await KnowledgeUploadTaskDao.update_latest_by_title(doc_title)

            # 是否需要MinerU解析（PDF/DOCX/XLSX需要解析，MD直接落库）
            parse_required = BooleanCharFlag.YES.value if ext in cls.PARSE_TYPES else BooleanCharFlag.NO.value
            record = KnowledgeUploadDocumentParseTask(
                doc_title=doc_title,  # 文档标题（优先使用上传参数，否则取文件名）
                doc_desc=upload_model.doc_desc,  # 文档描述
                doc_name=filename,  # 原始文件名
                doc_type=ext.upper(),  # 文档格式（如 PDF/DOC/DOCX/XLSX/MD）
                doc_version=next_version,  # 文档版本号（上传时预占）
                is_latest=BooleanCharFlag.YES.value,  # 标记为最新版本
                version_remark=upload_model.version_remark,  # 版本说明
                parse_required=parse_required,  # 是否需要MinerU解析（1-是 0-否）
                original_doc_key=original_doc_key,  # MinIO上的原始文件对象键
                total_pages=FileUtil.resolve_total_pages(temp_path, ext) if parse_required == BooleanCharFlag.YES.value else 0,
                # 总页数（从临时文件解析）
                status=DocumentUploadStatus.PENDING.value,  # 初始状态：待处理
                user_id=user_id,  # 上传用户ID
                dept_id=dept_id,  # 部门ID
                create_by=user_name,  # 创建者
                update_by=user_name,  # 更新者
            )
            record = await KnowledgeUploadTaskDao.add_task(record)

            if ext != 'md':
                # PDF/DOC/DOCX/XLSX 创建解析任务
                parse_task = KnowledgeMineruParseTask(
                    task_id=record.task_id,  # 关联上传任务ID
                    parse_mode=upload_model.parse_mode or 'document',  # 解析模式：html/document
                    enable_formula=upload_model.enable_formula or FormulaSwitch.YES.value,  # 公式识别（0-否 1-是）
                    enable_table=upload_model.enable_table or TableSwitch.YES.value,  # 表格识别（0-否 1-是）
                    language=upload_model.language or 'ch',  # 文档语言
                    is_ocr=upload_model.is_ocr or OcrSwitch.NO.value,  # OCR开关（0-否 1-是）
                    status=MineruParseTaskStatus.PENDING.value,  # 初始状态：待处理
                    user_id=user_id,
                    dept_id=dept_id,
                    create_by=user_name,
                    update_by=user_name,
                )
                # 持久化解析任务；消息由 upload_document 在事务提交后发布
                await KnowledgeMineruParseTaskDao.add_task(parse_task)
                return (
                    UploadDocumentResponseModel(**CamelCaseUtil.transform_result(record)),
                    parse_task.parse_task_id,
                )

            # MD 直接落库
            await cls._create_knowledge_document(record, original_doc_key, user_name)  # 创建知识库文档并落库
            await KnowledgeUploadTaskDao.update_status(record.task_id,
                                                         DocumentUploadStatus.CONVERTED.value)  # 更新上传任务状态为"已转换"
            record.status = DocumentUploadStatus.CONVERTED.value  # 同步内存记录状态
            return UploadDocumentResponseModel(**CamelCaseUtil.transform_result(record)), None

        finally:
            # 清理临时文件
            await FileUtil.clean_temp_file(temp_path)

    @classmethod
    async def _create_knowledge_document(
            cls,
            record: KnowledgeUploadDocumentParseTask,
            doc_key: str,
            user_name: str,
    ) -> KnowledgeDocument:
        """创建 knowledge_document 并处理 is_latest"""
        await KnowledgeDocumentDao.update_latest_by_title(record.doc_title)
        max_version = await KnowledgeDocumentDao.get_max_version_by_title(record.doc_title)
        is_latest = BooleanCharFlag.YES.value
        if max_version and record.doc_version < max_version:
            is_latest = BooleanCharFlag.NO.value

        document = KnowledgeDocument(
            task_id=record.task_id,
            source_type=DocumentSourceType.UPLOAD.value,
            doc_title=record.doc_title,
            doc_desc=record.doc_desc,
            doc_name=record.doc_name,
            doc_type=record.doc_type,
            original_doc_key=record.original_doc_key,
            doc_key=doc_key,
            doc_version=record.doc_version,
            is_latest=is_latest,
            version_remark=record.version_remark,
            status=DocumentStatus.CONVERTED.value,
            user_id=record.user_id,
            dept_id=record.dept_id,
            create_by=user_name,
            update_by=user_name,
        )
        return await KnowledgeDocumentDao.add_document(document)

    @classmethod
    async def _publish_parse_pending(cls, parse_task_id: int) -> None:
        """发布 document.parse.pending 消息"""
        try:
            await MessageStreamService.produce(
                topic=StreamTopicConfig.document_parse_pending,
                value=DocumentParsePending(parse_task_id=parse_task_id),
                key=str(parse_task_id),
            )
        except Exception as e:
            logger.exception(
                '发布 {} 消息失败: parse_task_id={}, error={}',
                StreamTopicConfig.document_parse_pending, parse_task_id, e,
            )
            raise ServiceException(f'发布解析消息失败: {e}') from e

    @classmethod
    async def publish_md_pending(cls, task_id: int) -> None:
        """发布 document.md.pending 消息"""
        try:
            await MessageStreamService.produce(
                topic=StreamTopicConfig.document_md_pending,
                value=DocumentMdPending(task_id=task_id),
                key=str(task_id),
            )
        except Exception as e:
            err = format_exception_message(e)
            logger.exception(
                '发布 {} 消息失败: task_id={}, error={}',
                StreamTopicConfig.document_md_pending, task_id, err,
            )
            raise ServiceException(f'发布 MD 合并消息失败: {err}') from e

    @classmethod
    async def list_records(
            cls,
            query_object: ListDocumentRecordsQueryModel,
            data_scope_sql: ColumnElement | None = None,
    ) -> PageModel[ListDocumentRecordsResponseModel]:
        """查询上传记录列表（含数据权限过滤）"""
        result = await KnowledgeUploadTaskDao.get_task_list(
            query_object, data_scope_sql=data_scope_sql, is_page=True,
        )
        # 将原始 dict 行转型为类型明确的响应 VO，与 response_model 声明一致
        result.rows = [ListDocumentRecordsResponseModel(**row) for row in result.rows]
        return result

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def delete_record(cls, task_id: int) -> None:
        """删除上传任务（仅允许未落库文档）"""
        
        # 分布式锁：防止同时删除同一条记录
        lock_key = LockKey.upload_task_key(task_id)
        async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
            if not acquired:
                raise ServiceException('该记录正在处理中，请稍后重试')
            
            current_user = RequestContext.get_current_user()
            user_name = current_user.user.user_name
            record = await KnowledgeUploadTaskDao.get_task_by_id(task_id)
            if not record:
                raise ServiceException('上传任务不存在')

            document = await KnowledgeDocumentDao.get_document_by_task_id(task_id, source_type=DocumentSourceType.UPLOAD.value)
            if document:
                raise ServiceException('已生成文档，不允许删除')

            await KnowledgeUploadTaskDao.soft_delete(task_id, update_by=user_name)
            await KnowledgeMineruParseTaskDao.soft_delete_by_upload_task_id(task_id, update_by=user_name)

    # endregion

    # region 解析任务查询

    @classmethod
    async def get_parse_task(cls, parse_task_id: int) -> GetParseTaskResponseModel:
        """获取解析任务详情"""
        task = await KnowledgeMineruParseTaskDao.get_task_by_id(parse_task_id)
        if not task:
            raise ServiceException('解析任务不存在')
        return GetParseTaskResponseModel(**CamelCaseUtil.transform_result(task))

    @classmethod
    async def get_parse_task_details(cls, parse_task_id: int) -> list[GetParseTaskDetailsResponseModel]:
        """获取解析任务分段明细"""
        details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_id(parse_task_id)
        return [GetParseTaskDetailsResponseModel(**CamelCaseUtil.transform_result(d)) for d in details]

    @classmethod
    async def get_parse_tasks_by_record(cls, task_id: int) -> list[ParseTaskItemResponseModel]:
        """获取上传任务下的所有解析任务列表"""
        tasks = await KnowledgeMineruParseTaskDao.get_tasks_by_upload_task_id(task_id)
        return [ParseTaskItemResponseModel(**CamelCaseUtil.transform_result(t)) for t in tasks]

    @classmethod
    async def handle_parse_decision(
            cls,
            parse_task_id: int,
            decision: HandleParseDecisionModel,
    ) -> None:
        """
        处理用户决策

        落库在事务内完成并提交后，再发布 document.parse.pending。
        """
        new_parse_task_id = await cls._handle_parse_decision(parse_task_id, decision)
        if new_parse_task_id is not None:
            await cls._publish_parse_pending(new_parse_task_id)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _handle_parse_decision(
            cls,
            parse_task_id: int,
            decision: HandleParseDecisionModel,
    ) -> int | None:
        """
        处理用户决策的落库部分。

        :return: 需发消息的新 parse_task_id；删除操作返回 None
        """
        # 先查询任务获取 task_id
        task = await KnowledgeMineruParseTaskDao.get_task_by_id(parse_task_id)
        if not task:
            raise ServiceException('解析任务不存在')

        # 分布式锁：基于 task_id，与删除接口互斥
        lock_key = LockKey.upload_task_key(task.task_id)
        async with DistributedLock(lock_key, expire=60, timeout=0) as acquired:
            if not acquired:
                raise ServiceException('该记录正在处理中，请稍后重试')

            user_name = decision.userInfo.user.user_name
            record = await KnowledgeUploadTaskDao.get_task_by_id(task.task_id)
            if not record:
                raise ServiceException('上传任务不存在')
            # 删除
            if decision.action == ParseDecisionAction.DELETE:
                await cls.delete_record(record.task_id)
                return None

            # 重试
            if decision.action != ParseDecisionAction.RETRY:
                raise ServiceException('仅支持删除和重试操作')

            if task.status != MineruParseTaskStatus.FAILED.value:
                raise ServiceException('仅 FAILED 状态任务可重试')
            if record.status != DocumentUploadStatus.USER_DECISION.value:
                raise ServiceException('上传记录不在用户决策状态')

            # 旧任务标记为 COMPLETED，旧失败分段标记为 RETRIED
            await KnowledgeMineruParseTaskDao.update_status(
                parse_task_id, MineruParseTaskStatus.COMPLETED.value
            )
            failed_details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_id(
                parse_task_id, state=MineruParseDetailState.PARSE_FAILED.value
            )
            await KnowledgeMineruParseDetailTaskDao.batch_update_state(
                [d.detail_id for d in failed_details], state=MineruParseDetailState.RETRIED.value
            )

            # 创建新任务
            new_task = KnowledgeMineruParseTask(
                task_id=record.task_id,
                parse_mode=task.parse_mode,
                enable_formula=task.enable_formula,
                enable_table=task.enable_table,
                language=task.language,
                is_ocr=task.is_ocr,
                status=MineruParseTaskStatus.PENDING.value,
                user_id=task.user_id,
                dept_id=task.dept_id,
                create_by=user_name,
                update_by=user_name,
            )
            new_task = await KnowledgeMineruParseTaskDao.add_task(new_task)

            # 为新任务创建分段记录（沿用旧失败分段的序号和页码范围）
            new_details = [
                KnowledgeMineruParseDetailTask(
                    parse_task_id=new_task.parse_task_id,
                    sequence_number=d.sequence_number,
                    page_ranges=d.page_ranges,
                    state=MineruParseDetailState.WAITING_UPLOAD.value,
                    create_by=user_name,
                    update_by=user_name,
                )
                for d in failed_details
            ]
            await KnowledgeMineruParseDetailTaskDao.batch_add_details(new_details)

            # 上传任务改为 PENDING
            await KnowledgeUploadTaskDao.update_status(
                record.task_id, DocumentUploadStatus.PENDING.value
            )
            return new_task.parse_task_id

    @classmethod
    async def _apply_upload_urls(
            cls,
            record: KnowledgeUploadDocumentParseTask,
            task: KnowledgeMineruParseTask,
            existing_details: list[KnowledgeMineruParseDetailTask]
    ) -> MinerUApplyUploadUrlsVo:
        """向 MinerU 申请批量上传链接"""

        # 生成页码范围与 MinerU 文件项
        client = MineUClient()
        file_items: list[MinerUFileItem] = client.build_file_items(
            file_name=record.doc_name,
            total_pages=record.total_pages,
            prefix='doc',
            is_ocr=task.is_ocr == OcrSwitch.YES.value,
        )
        # 重试 只保留页码范围一致的文件项
        if existing_details:
            file_items_existing = []
            for detail in existing_details:
                item: MinerUFileItem = file_items[detail.sequence_number]
                if not item or item.page_ranges != detail.page_ranges:
                    continue
                file_items_existing.append(item)
            file_items = file_items_existing

        request = MinerUBatchUploadReqVo(
            files=file_items,
            parse_mode=MinerUParseModeEnum.from_document_mode(task.parse_mode),
            enable_formula=task.enable_formula == FormulaSwitch.YES.value,
            enable_table=task.enable_table == TableSwitch.YES.value,
            language=task.language or 'ch',
        )
        return await client.apply_upload_urls(request)

    @classmethod
    async def _upload_segments(
            cls,
            record: KnowledgeUploadDocumentParseTask,
            file_urls: list[str],
    ) -> list[bool]:
        """下载源文件到本地后，上传至 MinerU 预签名链接

        不切分文件，所有分段均上传同一份完整源文件，
        MinerU 根据 page_ranges 参数自行处理页码范围。
        上传结束后删除本地下载文件，避免磁盘堆积。
        """
        if not record.original_doc_key:
            raise ServiceException('原始文件对象键为空')

        # 1. 下载源文件到本地（大文件落盘，避免整文件进内存）
        download_result = await KnowledgeMinioService.download_file(record.original_doc_key)
        source_path = download_result.local_path
        try:
            # 2. 所有分段均指向同一份完整源文件，MinerU 自行按 page_ranges 解析
            segment_paths = [source_path] * len(file_urls)

            # 3. 调用 MinerU 客户端上传本地文件
            client = MineUClient()
            result = await client.upload_files(file_urls, segment_paths)
            return result.upload_results
        finally:
            await FileUtil.clean_temp_file(source_path)

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def process_pending_task(cls, parse_task_id: int) -> None:
        """
        处理 PENDING 状态的解析任务（Stage2 消费者入口）

        :param parse_task_id: 解析任务ID
        """

        task = await KnowledgeMineruParseTaskDao.get_task_by_id(parse_task_id)
        if not task or task.status not in (MineruParseTaskStatus.PENDING.value, MineruParseTaskStatus.LINK_FAILED.value):
            logger.info(f'解析任务不存在或状态非 PENDING/LINK_FAILED, 跳过: parse_task_id={parse_task_id}')
            return

        record = await KnowledgeUploadTaskDao.get_task_by_id(task.task_id)
        if not record:
            logger.info(f'上传任务不存在: task_id={task.task_id}')
            return

        existing_details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_id(parse_task_id)
        is_retry = len(existing_details) > 0
        global apply_result
        try:
            # 申请批量上传链接
            apply_result = await cls._apply_upload_urls(record, task, existing_details)
        except Exception as e:
            # 申请上传链接失败，重新抛出让 @transactional 回滚，由调用方更新状态
            logger.exception('Stage2 处理失败: parse_task_id={}, error={}', parse_task_id, e)
            raise

        batch_id = apply_result.batch_id
        file_urls = apply_result.file_urls
        data_ids = apply_result.data_ids
        page_ranges = apply_result.page_ranges

        # 更新任务状态为 WAITING_UPLOAD
        await KnowledgeMineruParseTaskDao.update_status(
            parse_task_id=parse_task_id,
            status=MineruParseTaskStatus.WAITING_UPLOAD.value,
            batch_id=batch_id,
            clear_errors=True,
        )
        # 更新上传任务状态为 WAITING_UPLOAD
        await KnowledgeUploadTaskDao.update_status(
            task_id=record.task_id, status=DocumentUploadStatus.WAITING_UPLOAD.value, clear_errors=True
        )

        # 生成分段上传链接过期时间
        expire_at = task.create_time + timedelta(hours=cls.UPLOAD_EXPIRE_HOURS, minutes=cls.UPLOAD_EXPIRE_MINUTES)
        detail_ids = []

        if is_retry:
            # 重试时更新已有分段记录（batch_id、data_id、上传链接等可能变化）
            for idx, detail in enumerate(existing_details):
                await KnowledgeMineruParseDetailTaskDao.update_detail(
                    detail_id=detail.detail_id,
                    batch_id=batch_id,
                    data_id=data_ids[idx],
                    state=MineruParseDetailState.WAITING_UPLOAD.value,
                    upload_url=file_urls[idx],
                    upload_expire_at=expire_at,
                )
                detail_ids.append(detail.detail_id)
        else:
            # 首次执行，按顺序生成分段序号
            new_details = [
                KnowledgeMineruParseDetailTask(
                    parse_task_id=parse_task_id,
                    sequence_number=idx + 1,
                    batch_id=batch_id,
                    data_id=data_ids[idx],
                    page_ranges=pr,
                    state=MineruParseDetailState.WAITING_UPLOAD.value,
                    upload_url=file_urls[idx],
                    upload_expire_at=expire_at,
                    create_by='admin',
                    update_by='admin',
                )
                for idx, pr in enumerate(page_ranges)
            ]
            await KnowledgeMineruParseDetailTaskDao.batch_add_details(new_details)
            detail_ids = [d.detail_id for d in new_details]

        # 上传分段文件到 MinerU 预签名链接
        upload_results = await cls._upload_segments(record, file_urls)

        parsing_count = 0  # 上传成功分段计数
        failed_count = 0  # 上传失败分段计数
        for idx, success in enumerate(upload_results):
            if success:
                # 上传成功 → 进入解析中
                state = MineruParseDetailState.PARSING.value
                parsing_count += 1
            else:
                # 上传失败 → 标记失败
                state = MineruParseDetailState.UPLOAD_FAILED.value
                failed_count += 1
            # 逐条更新分段状态
            await KnowledgeMineruParseDetailTaskDao.update_detail(detail_ids[idx], state=state)
        # 全部成功 → 进入解析中
        if parsing_count == len(upload_results):
            await KnowledgeMineruParseTaskDao.update_status(parse_task_id, MineruParseTaskStatus.PARSING.value, clear_errors=True)
            await KnowledgeUploadTaskDao.update_status(record.task_id, DocumentUploadStatus.PARSING.value, clear_errors=True)
            return
        # 全部失败 → 标记上传中
        if failed_count == len(upload_results):
            await KnowledgeMineruParseTaskDao.update_status(parse_task_id, MineruParseTaskStatus.UPLOADING.value)
            await KnowledgeUploadTaskDao.update_status(record.task_id, DocumentUploadStatus.UPLOADING.value)
            return

        # 部分成功 → 进入解析中 不影响后续获取结果针对分段获取结果
        await KnowledgeMineruParseTaskDao.update_status(parse_task_id, MineruParseTaskStatus.PARSING.value, clear_errors=True)
        await KnowledgeUploadTaskDao.update_status(record.task_id, DocumentUploadStatus.PARSING.value, clear_errors=True)

    # endregion

    # region Stage4 Markdown 合并入库

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def process_md_pending(cls, task_id: int) -> None:
        """
        Stage4 消费者：合并 Markdown 并入库

        :param task_id: 上传任务ID
        """
        record = await KnowledgeUploadTaskDao.get_task_by_id(task_id)
        if not record:
            logger.warning(f'上传任务不存在: task_id={task_id}')
            return

        # 状态守卫：已转换或需用户决策的终态记录无需再次处理
        if record.status in (
            DocumentUploadStatus.CONVERTED.value,
            DocumentUploadStatus.USER_DECISION.value,
        ):
            logger.info(f'上传任务已是终态({record.status}), 跳过: task_id={task_id}')
            return

        active_task = await KnowledgeMineruParseTaskDao.get_active_task_by_upload_task_id(task_id)
        if active_task:
            logger.info(f'存在进行中的解析任务, 跳过: task_id={task_id}')
            return

        try:
            # 查询该上传任务下已完成（即所有分段均已上传完毕）的解析任务列表
            completed_tasks = await KnowledgeMineruParseTaskDao.get_tasks_by_upload_task_id_and_status(
                task_id, MineruParseTaskStatus.COMPLETED.value
            )
            # 提取已完成任务的 parse_task_id，用于下一步查询分段明细
            parse_task_ids = [task.parse_task_id for task in completed_tasks]
            # 获取所有已完成任务中状态为「已解析」的分段明细，作为合并 Markdown 的输入
            all_details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_ids(
                parse_task_ids, state=MineruParseDetailState.PARSED.value
            )

            if not all_details:
                logger.warning(f'没有可合并的解析分段: task_id={task_id}')
                return

            all_details.sort(key=lambda d: d.sequence_number)

            # 将 ORM 模型转换为 VO，供 MineruZipMergeService 使用（与 ORM 解耦）
            segment_vos = [
                MineruZipSegmentVo(
                    sequence_number=d.sequence_number,
                    full_zip_url=d.full_zip_url,
                )
                for d in all_details
            ]

            # 下载所有已完成分段的 zip 包 → 解压提取 Markdown 内容和图片
            merge_result = await MineruZipMergeService.download_and_extract_details(segment_vos)

            # 若存在图片映射，将 Markdown 中本地相对路径引用替换为 MinIO 可访问 URL
            if merge_result.image_map:
                merge_result.merged_markdown = (
                    await MineruZipMergeService.replace_image_references(
                        merge_result.merged_markdown,
                        merge_result.image_map,
                        record.task_id,
                    )
                )

            # 保存最终合并的 Markdown 至 MinIO，并创建 knowledge_document 版本记录
            await cls._save_final_markdown(record, merge_result.merged_markdown)

        except Exception as e:
            logger.exception('Stage4 md 合并失败: task_id={}, error={}', task_id, e)
            raise

    @classmethod
    async def _save_final_markdown(cls, record: KnowledgeUploadDocumentParseTask, markdown: str) -> None:
        """保存最终 Markdown 到 MinIO 并创建 knowledge_document"""
        object_name = f'{MinioConfig.minio_object_markdown_prefix}/{record.task_id}/{record.doc_title}.md'
        await KnowledgeMinioService.upload_stream(markdown.encode('utf-8'), object_name)
        doc_key = object_name

        # 检查是否已存在相同标题+版本的文档，若存在则更新而非插入（防重复）
        existing = await KnowledgeDocumentDao.get_document_by_title_and_version(
            record.doc_title, record.doc_version
        )
        if existing:
            db = get_current_session()
            existing.task_id = record.task_id
            existing.source_type = DocumentSourceType.UPLOAD.value
            existing.doc_desc = record.doc_desc
            existing.doc_name = record.doc_name
            existing.doc_type = record.doc_type
            existing.original_doc_key = record.original_doc_key
            existing.doc_key = doc_key
            existing.version_remark = record.version_remark
            existing.status = DocumentStatus.CONVERTED.value
            existing.update_by = record.update_by
            existing.update_time = datetime.now()
            await db.flush()
            # 更新 is_latest：将同标题的其他文档置为非最新
            await KnowledgeDocumentDao.update_latest_by_title(
                record.doc_title, exclude_doc_id=existing.doc_id
            )
            existing.is_latest = BooleanCharFlag.YES.value
            await db.flush()
        else:
            await KnowledgeDocumentDao.update_latest_by_title(record.doc_title)
            max_version = await KnowledgeDocumentDao.get_max_version_by_title(record.doc_title)
            is_latest = BooleanCharFlag.YES.value
            if max_version and record.doc_version < max_version:
                is_latest = BooleanCharFlag.NO.value

            document = KnowledgeDocument(
                task_id=record.task_id,
                source_type=DocumentSourceType.UPLOAD.value,
                doc_title=record.doc_title,
                doc_desc=record.doc_desc,
                doc_name=record.doc_name,
                doc_type=record.doc_type,
                original_doc_key=record.original_doc_key,
                doc_key=doc_key,
                doc_version=record.doc_version,
                is_latest=is_latest,
                version_remark=record.version_remark,
                status=DocumentStatus.CONVERTED.value,
                user_id=record.user_id,
                dept_id=record.dept_id,
                create_by=record.create_by,
                update_by=record.update_by,
            )
            await KnowledgeDocumentDao.add_document(document)

        await KnowledgeUploadTaskDao.update_status(
            record.task_id, DocumentUploadStatus.CONVERTED.value, clear_errors=True
        )

    # endregion

    @classmethod
    async def _converge_batch(cls, parse_task_id: int) -> None:
        """判断 batch 下是否全部超时失败，收敛任务/记录状态"""
        all_details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_id(parse_task_id)
        if not all_details:
            return

        all_failed = all(
            d.state == MineruParseDetailState.PARSE_FAILED.value for d in all_details
        )
        # 如果所有分段都失败了，则更新状态为分段全部解析失败/上传超时（终态），等待用户决策
        if all_failed:
            task_id = all_details[0].parse_task_id
            task = await KnowledgeMineruParseTaskDao.get_task_by_id(task_id)
            if task:
                await KnowledgeMineruParseTaskDao.update_status(
                    task_id,
                    MineruParseTaskStatus.FAILED.value,
                    error_code='UPLOAD_TIMEOUT',
                    error_message='所有分段上传链接均已过期',
                )
                await KnowledgeUploadTaskDao.update_status(
                    task.task_id,
                    DocumentUploadStatus.USER_DECISION.value,
                    error_code='UPLOAD_TIMEOUT',
                    error_message='所有分段上传链接均已过期',
                )
                logger.info(f'[Stage2-B] batch 全部超时失败: batch_id={parse_task_id}')

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def stage2_path_b_upload_failed(cls, parse_task_id: int, batch_details: list[KnowledgeMineruParseDetailTask]):
        # 1. 如果有分段上传链接已经超时，则更新该批次所有分段为失败
        #    （同一batch的上传链接过期时间一致）
        now = datetime.now()
        expired = any(
            d.upload_expire_at and d.upload_expire_at < now
            for d in batch_details
        )
        if expired:
            detail_ids = [d.detail_id for d in batch_details]
            await KnowledgeMineruParseDetailTaskDao.batch_update_state(
                detail_ids, MineruParseDetailState.PARSE_FAILED.value
            )
            logger.info(f'[Stage2-B] 分段上传链接已过期, 标记为PARSE_FAILED: '
                        f'parse_task_id={parse_task_id}, count={len(batch_details)}')
            # 3. 收敛任务/记录状态
            await cls._converge_batch(parse_task_id)
            return

        # 2. 未超时则复用现有 upload_url 重新上传
        task = await KnowledgeMineruParseTaskDao.get_task_by_id(parse_task_id)
        if not task:
            logger.warning(f'[Stage2-B] 解析任务不存在: parse_task_id={parse_task_id}')
            return

        record = await KnowledgeUploadTaskDao.get_task_by_id(task.task_id)
        if not record:
            logger.warning(f'[Stage2-B] 上传任务不存在: task_id={task.task_id}')
            return

        file_urls = [d.upload_url for d in batch_details]
        upload_results = await cls._upload_segments(record, file_urls)

        # 根据上传结果按 detail_id 分组，批量更新状态（一条 SQL IN 代替逐条更新）
        success_ids = [batch_details[idx].detail_id for idx, s in enumerate(upload_results) if s]
        if success_ids:
            await KnowledgeMineruParseDetailTaskDao.batch_update_state(
                success_ids, MineruParseDetailState.PARSING.value
            )
        failed_ids = [batch_details[idx].detail_id for idx, s in enumerate(upload_results) if not s]
        if failed_ids:
            await KnowledgeMineruParseDetailTaskDao.batch_update_state(
                failed_ids, MineruParseDetailState.UPLOAD_FAILED.value
            )

        # 3. 收敛任务/记录状态
        await cls._converge_batch(parse_task_id)

    # region Stage3 轮询解析结果

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def poll_parse_results(cls, parse_task_id: int, task_id: int, batch_id: str) -> bool:
        """
        Stage3：轮询单次 MinerU 解析结果并收敛状态

        :param parse_task_id: 解析任务ID
        :param task_id: 上传任务ID
        :param batch_id: MinerU 批次ID
        """
        client = MineUClient()
        batch_result = await client.get_batch_results(batch_id)
        details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_id(parse_task_id)

        # 建立 data_id -> detail 映射
        detail_map = {d.data_id: d for d in details if d.data_id}

        for result in batch_result.extract_result:
            detail = detail_map.get(result.data_id)
            if not detail:
                continue
            if result.state == 'done':
                # 解析完成 
                await KnowledgeMineruParseDetailTaskDao.update_detail(
                    detail.detail_id,
                    state=MineruParseDetailState.PARSED.value,
                    full_zip_url=result.full_zip_url,
                )
            elif result.state == 'failed':
                # 解析失败
                await KnowledgeMineruParseDetailTaskDao.update_detail(
                    detail.detail_id,
                    state=MineruParseDetailState.PARSE_FAILED.value,
                    err_msg=result.err_msg,
                )

        # 重新查询 DB 获取更新后的最新状态（上述 MinerU 结果更新未同步到内存中的 details）
        fresh_details = await KnowledgeMineruParseDetailTaskDao.get_details_by_task_id(parse_task_id)
        # 收敛：排除已重试的历史分段（RETRIED），仅对当前有效分段做状态收敛
        active_details = [d for d in fresh_details if d.state != MineruParseDetailState.RETRIED.value]

        # 检查是否仍有未收敛的分段（仍在处理中或等待重试）
        has_pending = any(
            d.state in (
                MineruParseDetailState.WAITING_UPLOAD.value,
                MineruParseDetailState.UPLOAD_FAILED.value,
                MineruParseDetailState.PARSING.value,
            )
            for d in active_details
        )
        if has_pending:
            # 仍有分段未确认终态，暂不收敛任务/记录状态，等待下一轮轮询
            logger.info(
                f'[Stage3] 仍有分段未确认终态，暂不收敛任务/记录状态，等待下一轮轮询: parse_task_id={parse_task_id}')
            return False

        # 所有有效分段均解析成功 → 任务完成
        all_done = all(d.state == MineruParseDetailState.PARSED.value for d in active_details)
        # 存在有效分段解析失败 → 部分失败
        any_failed = any(d.state == MineruParseDetailState.PARSE_FAILED.value for d in active_details)

        if all_done:
            await KnowledgeMineruParseTaskDao.update_status(
                parse_task_id, MineruParseTaskStatus.COMPLETED.value, clear_errors=True
            )
            await KnowledgeUploadTaskDao.update_status(
                task_id, DocumentUploadStatus.COMPLETED.value, clear_errors=True
            )
            # 通知调度器在锁外发布 Stage4 消息
            return True

        if any_failed:
            await KnowledgeMineruParseTaskDao.update_status(
                parse_task_id,
                MineruParseTaskStatus.FAILED.value,
                error_code='PARSE_FAILED',
                error_message='部分分段解析失败',
            )
            await KnowledgeUploadTaskDao.update_status(
                task_id,
                DocumentUploadStatus.USER_DECISION.value,
                error_code='PARSE_FAILED',
                error_message='部分分段解析失败',
            )
            return False

        return False

    # endregion
