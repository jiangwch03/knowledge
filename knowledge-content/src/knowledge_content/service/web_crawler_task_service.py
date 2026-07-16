import json
from datetime import datetime

from sqlalchemy import ColumnElement

from knowledge_common.common.aspect.data_scope import GetDataScope
from knowledge_common.common.context import RedisContext, RequestContext
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import PageModel
from knowledge_common.config.env import Crawl4aiConfig, StreamTopicConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.redis import DistributedLock, LockKey, RedisKey
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_url_record_status_enum import CrawlUrlRecordStatus
from knowledge_content.mapper.dao.web_crawler_task_dao import WebCrawlerTaskDao
from knowledge_content.mapper.do.web_crawler_task_do import WebCrawlerTask
from knowledge_content.mapper.vo.crawl_task_update_vo import CrawlTaskUpdateVo
from knowledge_content.service.document_service import DocumentService
from knowledge_content.service.vo.crawl_task_create_vo import CrawlTaskCreateVo
from knowledge_content.service.vo.message_stream_topic_vo import CrawlDocumentPending, CrawlTaskPending
from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import WebCrawlerTaskUrlRecordDao
from knowledge_content.vo.crawler_vo import UrlRecordRespVo
from knowledge_content.agents.utils.filter_chain_util import (
    compute_pages_to_remove,
    extract_filter_chain,
)
from knowledge_content.infra.minio.minio_client import MinioClient


class WebCrawlerTaskService:
    """
    爬取任务服务层

    负责任务 CRUD、状态更新、进度查询。
    """

    # 用户可在 Agent 中继续操作的任务状态
    ACTIONABLE_TASK_STATUSES: tuple[str, ...] = (
        CrawlTaskStatus.RUNNING.value,
        CrawlTaskStatus.PAUSED.value,
        CrawlTaskStatus.USER_DECISION.value,
        CrawlTaskStatus.FAILED.value,
    )

    @classmethod
    def _resolve_task_data_scope_sql(cls) -> ColumnElement:
        """根据当前登录用户构建任务表数据权限 SQL。"""
        current_user = RequestContext.get_current_user()
        return GetDataScope(WebCrawlerTask).build_scope_sql(current_user)

    @classmethod
    async def list_actionable_tasks(
        cls,
        page_num: int = 1,
        page_size: int = 20,
    ):
        """
        查询当前用户数据权限下、可继续操作的任务列表。

        仅包含 RUNNING / PAUSED / USER_DECISION / FAILED 状态。
        """
        return await WebCrawlerTaskDao.get_task_list(
            statuses=list(cls.ACTIONABLE_TASK_STATUSES),
            is_page=True,
            page_num=page_num,
            page_size=page_size,
            data_scope_sql=cls._resolve_task_data_scope_sql(),
        )

    @classmethod
    async def get_task_with_data_scope(cls, task_id: int) -> WebCrawlerTask:
        """
        获取任务并校验当前用户数据权限。

        :raises ServiceException: 任务不存在或无权访问
        """
        task = await WebCrawlerTaskDao.get_task_by_id_with_scope(
            task_id,
            cls._resolve_task_data_scope_sql(),
        )
        if task is None:
            raise ServiceException(message='任务不存在或无权访问')
        return task

    @classmethod
    async def find_latest_visible_task_by_url(cls, target_url: str) -> WebCrawlerTask | None:
        """
        按目标 URL 查询当前用户数据权限内可见的最新版本爬取任务。

        用于防重复爬取检查。返回 None 表示对用户不可见或未爬过，不区分具体原因。
        """
        normalized_url = target_url.strip()
        if not normalized_url:
            raise ServiceException(message='URL 不能为空')

        return await WebCrawlerTaskDao.get_latest_task_by_url_with_scope(
            normalized_url,
            cls._resolve_task_data_scope_sql(),
        )

    @classmethod
    async def get_latest_task_by_url_with_data_scope(cls, target_url: str) -> WebCrawlerTask:
        """
        按目标 URL 获取最新版本的爬取任务，并校验当前用户数据权限。

        :raises ServiceException: 未找到任务
        """
        task = await cls.find_latest_visible_task_by_url(target_url)
        if task is None:
            raise ServiceException(message=f'未找到该 URL 对应的爬取任务: {target_url.strip()}')
        return task

    @classmethod
    async def get_task(cls, task_id: int) -> WebCrawlerTask:
        """
        根据ID获取任务

        :param task_id: 任务ID
        :return: 任务对象
        :raises ServiceException: 任务不存在
        """
        task = await WebCrawlerTaskDao.get_task_by_id(task_id)
        if task is None:
            raise ServiceException(message='任务不存在')
        return task

    @classmethod
    async def get_task_list_services(
        cls,
        user_id: int | None = None,
        status: str | None = None,
        create_by: str | None = None,
        is_page: bool = True,
        page_num: int = 1,
        page_size: int = 20,
        data_scope_sql=None,
    ):
        """
        查询任务列表

        :return: 任务列表
        """
        return await WebCrawlerTaskDao.get_task_list(
            user_id=user_id,
            status=status,
            create_by=create_by,
            is_page=is_page,
            page_num=page_num,
            page_size=page_size,
            data_scope_sql=data_scope_sql,
        )

    @classmethod
    async def create_task(cls, vo: CrawlTaskCreateVo) -> WebCrawlerTask:
        """
        创建爬取任务

        :param vo: 任务创建参数VO
        :return: 任务对象
        """
        task = await cls._create_task(vo)

        # 触发后台异步执行（对话阶段与执行阶段解耦）
        await MessageStreamService.produce(
            topic=StreamTopicConfig.crawl_task_pending,
            value=CrawlTaskPending(task_id=task.task_id),
            key=str(task.task_id),
        )
        return task

    @classmethod
    async def _resolve_task_version_fields(cls, vo: CrawlTaskCreateVo) -> dict:
        """按 target_url 预分配文档版本号"""
        doc_version = await DocumentService.get_next_version(vo.target_url)
        return {'doc_version': doc_version}

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def _create_task(cls, vo: CrawlTaskCreateVo) -> WebCrawlerTask:

        # 步骤0：粗估总页面数（HTTP 请求，放事务外）
        estimated_pages = await WebCrawlerAnalysisService.estimate_total_pages(vo.target_url, vo.crawl_config)

        version_fields = await cls._resolve_task_version_fields(vo)

        # 步骤1：创建任务记录
        task = WebCrawlerTask(
            target_url=vo.target_url,  # 爬取目标URL
            crawl_config=json.dumps(vo.crawl_config, ensure_ascii=False),  # 爬取配置，JSON序列化存储
            status=CrawlTaskStatus.PENDING.value,  # 初始状态：待执行
            total_count=estimated_pages,  # 预估总页面数（步骤0粗估）
            max_retry_count=Crawl4aiConfig.crawl4ai_rule_retry_limit,  # 规则自动重试上限
            user_id=vo.user_id,  # 任务所属用户
            dept_id=vo.dept_id,  # 任务所属部门（可选）
            create_by=vo.create_by,  # 创建者标识
            update_by=vo.create_by,  # 首次插入时创建者即更新者
            **version_fields,
        )
        result = await WebCrawlerTaskDao.add_task(task)

        logger.info(
            f'[Task] 创建任务: task_id={result.task_id}, url={vo.target_url}, '
            f'doc_version={result.doc_version}, estimated_pages={estimated_pages}',
        )
        return result

    @classmethod
    async def retry_task(
        cls,
        task_id: int,
        crawl_config: dict | None = None,
        target_url: str | None = None,
        update_by: str = '',
        extend_max_retry: bool = False,
    ) -> dict:
        """
        重试任务：重置状态为 PENDING、递增重试计数、清空错误信息，并发布消息触发重新执行

        :param task_id: 任务ID
        :param crawl_config: 可选的新爬取策略配置（重试时调整参数后传入）
        :param target_url: 可选的新目标 URL（入口变更时传入；与原 URL 不同则重分配版本并清空旧 URL 记录）
        :param update_by: 更新者（登录名）
        :param extend_max_retry: True 时抬高 max_retry_count（+= crawl4ai_rule_retry_limit，LLM 人工重试专用）
        :return: 提交后的任务摘要（status / retry_count / max_retry_count / target_url），避免外层 session 脏读
        """
        # 入口变更时粗估页数走 HTTP，放事务外
        estimated_pages: int | None = None
        new_url = (target_url or '').strip() or None
        if new_url:
            task = await cls.get_task(task_id)
            if new_url != (task.target_url or '').strip():
                estimated_pages = await WebCrawlerAnalysisService.estimate_total_pages(
                    new_url, crawl_config,
                )

        # 步骤1：事务内重置状态并递增重试计数（可选更新配置 / 目标 URL）
        result = await cls._retry_task_in_transaction(
            task_id,
            crawl_config=crawl_config,
            target_url=new_url,
            estimated_pages=estimated_pages,
            update_by=update_by,
            extend_max_retry=extend_max_retry,
        )

        # 步骤2：事务提交后发布消息触发消费者重新执行
        await MessageStreamService.produce(
            topic=StreamTopicConfig.crawl_task_pending,
            value=CrawlTaskPending(task_id=task_id),
            key=str(task_id),
        )
        return result

    @classmethod
    @transactional()
    async def _retry_task_in_transaction(
        cls,
        task_id: int,
        crawl_config: dict | None = None,
        target_url: str | None = None,
        estimated_pages: int | None = None,
        update_by: str = '',
        extend_max_retry: bool = False,
    ) -> dict:
        """
        事务内重试任务：校验任务存在、重置状态为 PENDING、递增重试计数、清空错误信息

        :param task_id: 任务ID
        :param crawl_config: 可选的新爬取策略配置
        :param target_url: 可选的新目标 URL
        :param estimated_pages: 入口变更时预估页数
        :param update_by: 更新者（登录名）
        :param extend_max_retry: True 时抬高 max_retry_count（+= crawl4ai_rule_retry_limit）
        :return: 写入后的状态摘要
        """
        task = await cls.get_task(task_id)
        actor = update_by or task.create_by or ''
        new_url = (target_url or '').strip() or None
        url_changed = bool(new_url) and new_url != (task.target_url or '').strip()
        next_retry_count = (task.retry_count or 0) + 1
        default_limit = Crawl4aiConfig.crawl4ai_rule_retry_limit
        current_max = task.max_retry_count if task.max_retry_count is not None else default_limit
        next_max = (
            max(current_max + default_limit, next_retry_count)
            if extend_max_retry
            else current_max
        )
        effective_url = new_url if url_changed else (task.target_url or '').strip()

        update_kwargs: dict = {
            'status': CrawlTaskStatus.PENDING.value,
            'retry_count': next_retry_count,
            'clear_errors': True,
            'crawl_config': crawl_config,
            'update_by': actor,
        }
        if extend_max_retry:
            update_kwargs['max_retry_count'] = next_max
        if url_changed:
            assert new_url is not None
            doc_version = await DocumentService.get_next_version(new_url)
            update_kwargs.update({
                'target_url': new_url,
                'doc_version': doc_version,
                'progress': 0,
                'success_count': 0,
                'failed_count': 0,
                'total_count': estimated_pages if estimated_pages is not None else 0,
                'current_step': '',
            })
            await WebCrawlerTaskUrlRecordDao.soft_delete_by_task_id(task_id, update_by=actor)

        await WebCrawlerTaskDao.update_task(task_id, CrawlTaskUpdateVo(**update_kwargs))
        logger.info(
            f'[Task] 重试任务: task_id={task_id}, retry_count={next_retry_count}, '
            f'max_retry_count={next_max}, status={CrawlTaskStatus.PENDING.value}'
            + (f', target_url={new_url}' if url_changed else '')
        )
        return {
            'task_id': task_id,
            'status': CrawlTaskStatus.PENDING.value,
            'retry_count': next_retry_count,
            'max_retry_count': next_max,
            'target_url': effective_url,
            'url_changed': url_changed,
        }

    @classmethod
    async def requeue_after_process_died(cls, task_id: int) -> None:
        """
        进程中断后续跑：直接置 PENDING 并投递执行消息，不递增 retry_count。

        :param task_id: 任务ID
        """
        await cls.mark_pending_after_process_died(task_id)
        await MessageStreamService.produce(
            topic=StreamTopicConfig.crawl_task_pending,
            value=CrawlTaskPending(task_id=task_id),
            key=str(task_id),
        )

    @classmethod
    @transactional()
    async def mark_pending_after_process_died(cls, task_id: int) -> None:
        """
        进程中断：仅将任务置为 PENDING（不清空进度、不递增 retry_count）。

        调度器持锁场景应调用本方法，消息投递放到锁外，避免执行器抢锁失败。
        """
        task = await cls.get_task(task_id)
        await WebCrawlerTaskDao.update_task(
            task_id,
            CrawlTaskUpdateVo(
                status=CrawlTaskStatus.PENDING.value,
                clear_errors=True,
                current_step='进程中断，已自动续跑',
                update_by=task.create_by or '',
            ),
        )
        logger.info(
            f'[Task] 进程中断续跑: task_id={task_id}, retry_count={task.retry_count or 0}'
        )

    @classmethod
    @transactional()
    async def update_task_status(
        cls,
        task_id: int,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        clear_errors: bool = False,
    ) -> None:
        """
        更新任务状态

        :param task_id: 任务ID
        :param status: 目标状态
        :param error_code: 错误码
        :param error_message: 错误信息
        :param clear_errors: 是否清空错误信息
        """
        task = await cls.get_task(task_id)
        update_vo = CrawlTaskUpdateVo(
            status=status,
            error_code=error_code,
            error_message=error_message,
            clear_errors=clear_errors,
            update_by=task.create_by or '',
        )
        await WebCrawlerTaskDao.update_task(task_id, update_vo)
        logger.info(f'[Task] 更新状态: task_id={task_id}, status={status}')

    @classmethod
    @transactional()
    async def update_task_progress(
        cls,
        task_id: int,
        progress: int,
        current_step: str | None = None,
        success_count: int | None = None,
        failed_count: int | None = None,
        total_count: int | None = None,
    ) -> None:
        """
        更新任务进度
        """
        task = await cls.get_task(task_id)
        update_vo = CrawlTaskUpdateVo(
            progress=progress,
            current_step=current_step,
            success_count=success_count,
            failed_count=failed_count,
            total_count=total_count,
            update_by=task.create_by or '',
        )
        await WebCrawlerTaskDao.update_task(task_id, update_vo)

    @classmethod
    @transactional()
    async def start_task(cls, task_id: int) -> None:
        """
        标记任务开始执行
        """
        task = await cls.get_task(task_id)
        update_vo = CrawlTaskUpdateVo(
            status=CrawlTaskStatus.RUNNING.value,
            started_time=datetime.now(),
            current_step='开始执行爬取任务',
            update_by=task.create_by or '',
        )
        await WebCrawlerTaskDao.update_task(task_id, update_vo)

    @classmethod
    @transactional()
    async def complete_task(cls, task_id: int) -> None:
        """
        标记任务完成
        """
        task = await cls.get_task(task_id)
        update_vo = CrawlTaskUpdateVo(
            status=CrawlTaskStatus.COMPLETED.value,
            progress=100,
            completed_time=datetime.now(),
            current_step='爬取完成',
            update_by=task.create_by or '',
        )
        await WebCrawlerTaskDao.update_task(task_id, update_vo)

    @classmethod
    async def get_url_records_by_task(
        cls,
        task_id: int,
        page_num: int = 1,
        page_size: int = 20,
        status: str | None = None,
    ) -> PageModel:
        """
        获取任务URL记录

        从 knowledge_web_crawler_task_url_record 表中查询URL级别的爬取结果。

        :param task_id: 任务ID
        :param page_num: 页码
        :param page_size: 每页数量
        :param status: 状态过滤（'SUCCESS'/'FAILED'）
        :return: 分页的 URL 记录
        """
        page_model = await WebCrawlerTaskUrlRecordDao.get_records_by_task_id(
            task_id=task_id,
            status=status,
            is_page=True,
            page_num=page_num,
            page_size=page_size,
        )

        # 映射 DO -> VO
        # PageUtil.paginate 返回的 rows 经过 CamelCaseUtil.transform_result 转换，已是 camelCase dict
        records = []
        for r in (page_model.rows if hasattr(page_model, 'rows') else page_model):
            records.append(UrlRecordRespVo(
                id=r.get('id'),
                taskId=r.get('taskId'),
                url=r.get('url'),
                status=r.get('status', 'PENDING') or 'PENDING',
                docKey=r.get('docKey'),
                title=r.get('title') or '',
                statusCode=r.get('statusCode'),
                errorCode=r.get('errorCode'),
                errorMessage=r.get('errorMessage'),
                retryCount=r.get('retryCount', 0) or 0,
                createTime=r.get('createTime'),
            ))

        return PageModel[UrlRecordRespVo](
            rows=records,
            pageNum=page_model.page_num,
            pageSize=page_model.page_size,
            total=page_model.total,
            hasNext=page_model.has_next,
        )

    @classmethod
    async def pause_task(cls, task_id: int) -> None:
        """
        暂停爬取任务

        校验任务状态（仅允许 RUNNING），设置 Redis 暂停标志通知执行器停止。
        执行器检测到暂停标志后会将任务状态更新为 PAUSED。

        :param task_id: 任务ID
        :raises ServiceException: 任务不存在或状态不允许暂停
        """
        task = await cls.get_task(task_id)
        if not task:
            raise ServiceException(message=f'任务 {task_id} 不存在')

        if task.status != CrawlTaskStatus.RUNNING.value:
            raise ServiceException(
                message=f'只允许暂停执行中的任务，当前状态: {task.status}'
            )

        redis = RedisContext.get_redis()
        pause_key = RedisKey.crawl_task_pause_key(task_id)
        # TTL 10 分钟，对齐取消标志；覆盖单页爬取/后处理耗时，避免页间检查前标志过期
        await redis.setex(pause_key, 600, '1')
        logger.info('[Task] 已设置暂停标志: task_id={}', task_id)

    @classmethod
    async def resume_task(cls, task_id: int, update_by: str = '') -> None:
        """
        恢复暂停的爬取任务：PAUSED → PENDING，再发执行消息。

        写法同 create_task：先走 @transactional 落库并提交，再 produce。
        """
        async with DistributedLock(LockKey.crawl_task_key(task_id), expire=30, timeout=10) as acquired:
            if not acquired:
                raise ServiceException(message='任务正在处理中，请稍后重试')
            await cls._resume_task(task_id, update_by=update_by)

        await MessageStreamService.produce(
            topic=StreamTopicConfig.crawl_task_pending,
            value=CrawlTaskPending(task_id=task_id),
            key=str(task_id),
        )
        logger.info('[Task] 已发送恢复消息: task_id={}', task_id)

    @classmethod
    @transactional()
    async def _resume_task(cls, task_id: int, update_by: str = '') -> None:
        """校验 PAUSED 并改成 PENDING（提交后再由 resume_task 发消息）。"""
        task = await cls.get_task(task_id)
        if task.status != CrawlTaskStatus.PAUSED.value:
            raise ServiceException(
                message=f'只允许恢复已暂停的任务，当前状态: {task.status}'
            )
        await WebCrawlerTaskDao.update_task(
            task_id,
            CrawlTaskUpdateVo(
                status=CrawlTaskStatus.PENDING.value,
                update_by=update_by or task.create_by or '',
            ),
        )
        logger.info(f'[Task] 恢复任务: task_id={task_id}')

    @classmethod
    @transactional()
    async def update_crawl_config(
        cls,
        task_id: int,
        crawl_config: dict,
        target_url: str | None = None,
        update_by: str = '',
    ) -> None:
        """
        在 PAUSED 状态下更新 crawl_config（rescope 专用，不触发执行）

        :param task_id: 任务 ID
        :param crawl_config: 新 crawl4ai 策略 JSON
        :param target_url: 可选的新目标 URL（入口变更时传入）
        :raises ServiceException: 任务非 PAUSED
        """
        task = await cls.get_task(task_id)
        if task.status != CrawlTaskStatus.PAUSED.value:
            raise ServiceException(
                message=f'只允许在 PAUSED 状态下更新配置，当前状态: {task.status}'
            )

        actor = update_by or task.create_by or ''
        new_url = (target_url or '').strip() or None
        url_changed = bool(new_url) and new_url != (task.target_url or '').strip()
        effective_url = new_url if url_changed else (task.target_url or '').strip()

        estimated_pages = await WebCrawlerAnalysisService.estimate_total_pages(
            effective_url, crawl_config,
        )
        update_kwargs: dict = {
            'crawl_config': crawl_config,
            'total_count': estimated_pages,
            'update_by': actor,
        }
        if url_changed:
            assert new_url is not None
            update_kwargs['target_url'] = new_url
            update_kwargs['doc_version'] = await DocumentService.get_next_version(new_url)

        await WebCrawlerTaskDao.update_task(task_id, CrawlTaskUpdateVo(**update_kwargs))
        logger.info(
            '[Task] 已更新 crawl_config: task_id={}, estimated_pages={}'
            + (f', target_url={new_url}' if url_changed else ''),
            task_id, estimated_pages,
        )

    @classmethod
    async def apply_scope_change(
        cls,
        task_id: int,
        crawl_config: dict,
        urls_to_remove: list[str] | None = None,
        target_url: str | None = None,
        update_by: str = '',
    ) -> dict:
        """
        应用 rescope：PAUSED 下删页 → 更新 config（可改入口）→ resume

        不加外层 @transactional：内部删页/更新配置各自提交；resume 必须在 PENDING
        落库提交后再 produce（见 resume_task）。

        :return: 操作摘要 dict
        """
        async with DistributedLock(LockKey.crawl_task_key(task_id), expire=60, timeout=10) as acquired:
            if not acquired:
                raise ServiceException(message='任务正在处理中，请稍后重试')

            task = await cls.get_task(task_id)
            if task.status != CrawlTaskStatus.PAUSED.value:
                raise ServiceException(
                    message=f'apply_scope_change 要求任务为 PAUSED，当前: {task.status}。请先 pause_crawl_task。'
                )

            actor = update_by or task.create_by or ''
            removed_count = 0
            if urls_to_remove:
                removed_count = await cls._remove_urls_in_transaction(
                    task_id, urls_to_remove, update_by=actor,
                )

            await cls.update_crawl_config(
                task_id,
                crawl_config,
                target_url=target_url,
                update_by=actor,
            )

        # 锁外 resume：先提交 PENDING 再发消息
        await cls.resume_task(task_id, update_by=update_by or task.create_by or '')
        counts = await WebCrawlerTaskUrlRecordDao.count_by_status(task_id)
        return {
            'task_id': task_id,
            'removed_count': removed_count,
            'success_count': counts.get('SUCCESS', 0),
            'failed_count': counts.get('FAILED', 0),
        }

    @classmethod
    @transactional()
    async def _remove_urls_in_transaction(
        cls,
        task_id: int,
        urls: list[str],
        update_by: str = '',
    ) -> int:
        """
        软删 URL 记录、清理 MinIO 对象、重算 success/failed 计数

        :return: 实际删除的记录数
        """
        unique_urls = list(dict.fromkeys(u for u in urls if u))
        if not unique_urls:
            return 0

        records = await WebCrawlerTaskUrlRecordDao.get_records_by_urls(task_id, unique_urls)
        minio = MinioClient()
        for record in records:
            if record.doc_key:
                await minio.remove_object(record.doc_key)

        deleted = await WebCrawlerTaskUrlRecordDao.soft_delete_by_urls(task_id, unique_urls, update_by)
        counts = await WebCrawlerTaskUrlRecordDao.count_by_status(task_id)
        task = await cls.get_task(task_id)
        update_vo = CrawlTaskUpdateVo(
            success_count=counts.get(CrawlUrlRecordStatus.SUCCESS.value, 0),
            failed_count=counts.get(CrawlUrlRecordStatus.FAILED.value, 0),
            update_by=update_by or task.create_by or '',
        )
        await WebCrawlerTaskDao.update_task(task_id, update_vo)
        logger.info('[Task] rescope 删页: task_id={}, deleted={}', task_id, deleted)
        return deleted

    @classmethod
    async def preview_scope_removal(cls, task_id: int, crawl_config: dict) -> dict:
        """
        预览 rescope 待删 URL：查已爬 SUCCESS 页，按新 filter_chain 计算越界列表。

        只读，不修改任务；供 Supervisor 展示给用户确认后再 apply_scope_change。
        """
        await cls.get_task_with_data_scope(task_id)

        filter_chain = extract_filter_chain(crawl_config)
        if not filter_chain:
            return {
                'success': True,
                'task_id': task_id,
                'pages_to_remove': [],
                'urls_to_remove': [],
                'removed_count': 0,
                'crawled_success_count': 0,
                'summary': '新爬取配置中未解析到范围过滤规则，无需删除已爬页面；应用新范围时请传 urls_to_remove=[]',
            }

        records = await WebCrawlerTaskUrlRecordDao.get_all_records_by_task_id(
            task_id,
            status=CrawlUrlRecordStatus.SUCCESS.value,
        )
        crawled_pages = [
            {'url': r.url, 'title': r.title or '', 'status': r.status}
            for r in records
        ]
        pages_to_remove = compute_pages_to_remove(crawled_pages, filter_chain)
        urls_to_remove = [p['url'] for p in pages_to_remove]
        removed_count = len(urls_to_remove)
        crawled_success_count = len(crawled_pages)

        if removed_count == 0:
            summary = (
                f'按新爬取范围核对 {crawled_success_count} 个已成功页面，'
                '无需删除；应用新范围时请传 urls_to_remove=[]'
            )
        else:
            summary = (
                f'按新爬取范围需删除 {removed_count} 个已爬页面'
                f'（当前成功 {crawled_success_count} 个），请向用户确认后再应用新范围'
            )

        return {
            'success': True,
            'task_id': task_id,
            'pages_to_remove': pages_to_remove,
            'urls_to_remove': urls_to_remove,
            'removed_count': removed_count,
            'crawled_success_count': crawled_success_count,
            'summary': summary,
        }

    @classmethod
    async def persist_crawl_results(cls, task_id: int) -> str:
        """
        放弃失败的URL，将已成功爬取的页面提交到文档落库队列

        适用状态：FAILED / USER_DECISION / PAUSED / CONVERT_FAILED
        流程：校验状态 → 加锁互斥 → 查询成功URL记录 → 标记COMPLETED → 投递 crawl.document.pending

        :param task_id: 任务ID
        :return: 结果描述字符串（仅表示提交成功，不等待落库）
        :raises ServiceException: 状态不允许或无成功URL
        """
        logger.info('[PersistTask] 开始提交入库已爬内容: task_id={}', task_id)

        async with DistributedLock(LockKey.crawl_task_key(task_id), expire=60, timeout=3) as acquired:
            if not acquired:
                raise ServiceException(
                    message='任务正在处理中（重试运行/其他操作），请稍后重试'
                )

            task = await cls.get_task(task_id)

            allowed_statuses = {
                CrawlTaskStatus.FAILED.value,
                CrawlTaskStatus.USER_DECISION.value,
                CrawlTaskStatus.PAUSED.value,
                CrawlTaskStatus.CONVERT_FAILED.value,
            }
            if task.status not in allowed_statuses:
                raise ServiceException(
                    message=f'当前任务状态({task.status})不允许入库，'
                            f'仅 FAILED / USER_DECISION / PAUSED / CONVERT_FAILED 状态允许此操作'
                )

            success_records = await WebCrawlerTaskUrlRecordDao.get_success_records_with_doc_key(task_id)
            if not success_records:
                raise ServiceException(
                    message='没有成功爬取的URL记录，无法入库文档'
                )

            page_count = len(success_records)
            target_url = task.target_url

            await cls.complete_task(task_id)

        try:
            await MessageStreamService.produce(
                topic=StreamTopicConfig.crawl_document_pending,
                value=CrawlDocumentPending(task_id=task_id, target_url=target_url),
                key=str(task_id),
            )
            logger.info(
                '[PersistTask] 入库消息已投递: task_id={}, url_count={}',
                task_id, page_count,
            )
            return (
                f'入库已提交：{page_count} 个成功页面已进入文档落库队列，'
                f'系统将异步写入知识库文档。'
            )
        except Exception as e:
            logger.error('[PersistTask] 投递入库消息失败: task_id={}, error={}', task_id, e, exc_info=True)
            await cls.update_task_status(
                task_id,
                CrawlTaskStatus.CONVERT_FAILED.value,
                error_code=CrawlTaskErrorCode.DOC_PERSIST_ERROR.value,
                error_message=f'入库消息投递失败: {e}',
            )
            raise ServiceException(message=f'入库消息投递失败: {e}')

    # 旧名兼容
    merge_crawl_results = persist_crawl_results

    @classmethod
    @transactional()
    async def delete_task(cls, task_id: int, update_by: str = '') -> None:
        """
        软删除任务

        禁止删除正在执行（PENDING/RUNNING），以及已进入合并链路
        （COMPLETED/CONVERTING/CONVERTED，转换开始后不可删）的任务。
        使用分布式锁与消费者、决策接口互斥。
        """
        # 锁等待3秒，若消费者或定时任务正持有锁则放弃
        async with DistributedLock(LockKey.crawl_task_key(task_id), expire=30, timeout=3) as acquired:
            if not acquired:
                raise ServiceException(message='任务正在处理中，请稍后重试')

            task = await cls.get_task(task_id)
            blocked = {
                CrawlTaskStatus.PENDING.value,
                CrawlTaskStatus.RUNNING.value,
                CrawlTaskStatus.COMPLETED.value,
                CrawlTaskStatus.CONVERTING.value,
                CrawlTaskStatus.CONVERTED.value,
            }
            if task.status in blocked:
                raise ServiceException(message='该任务正在执行、落库中或已转换，不可删除')
            await WebCrawlerTaskDao.soft_delete(task_id, update_by)
            await WebCrawlerTaskUrlRecordDao.soft_delete_by_task_id(task_id, update_by)
            logger.info(f'[Task] 删除任务: task_id={task_id}')


