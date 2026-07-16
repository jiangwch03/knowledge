"""
爬取任务执行服务

负责调用 crawl4ai 执行实际网页爬取，处理爬取结果并持久化落库。
通过 CrawlPipelineService 编排流式爬取与后处理流程，PipelineService 内部通过 DistributedSemaphore 控制全局并发数。
"""

import json

from knowledge_common.common.context import RedisContext
from knowledge_common.config.env import Crawl4aiConfig, StreamTopicConfig
from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.redis import RedisKey
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.service.crawl_pipeline_service import CrawlPipelineService, TaskCancelledException, TaskPausedException
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo
from knowledge_content.service.vo.message_stream_topic_vo import CrawlDocumentPending
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService
from knowledge_content.mapper.dao.web_crawler_task_dao import WebCrawlerTaskDao
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import WebCrawlerTaskUrlRecordDao
from knowledge_content.mapper.vo.crawl_task_update_vo import CrawlTaskUpdateVo
from knowledge_content.vo.crawl_url_record_upsert_vo import UrlRecordUpsertVo
from knowledge_content.enums.crawl_url_record_status_enum import CrawlUrlRecordStatus
from knowledge_common.common.transactional import async_session_scope


class WebCrawlerTaskExecutorService:
    """
    爬取任务执行服务层

    负责编排爬取任务的完整执行链路，通过 Crawl4aiClient 调用爬取引擎。

    注意：本类未使用 @transactional 装饰器，这是有意为之的设计决策。
    各子操作（start_task / update_task_progress / update_task_status / complete_task）各自持有独立事务，
    execute_task 作为编排者不启动事务，以确保异常发生时能在独立新 session 中标记失败状态，
    避免因事务回滚导致 PendingRollbackError（详见事务异常与状态更新分离规范）。
    """

    @classmethod
    async def execute_task(cls, task_id: int) -> None:
        """
        执行爬取任务（入口）

        幂等守卫：先查任务状态，仅 PENDING 才执行，其余状态直接跳过，
        防止消息重复投递导致已处理完成的任务被重执行。

        清除可能残留的取消标志（如上次超时的 Redis 通知尚未过期），
        然后委托 _execute_task 完成实际执行链路。

        :param task_id: 任务ID
        """
        # 幂等守卫：仅 PENDING 状态的任务才执行
        task = await WebCrawlerTaskDao.get_task_by_id(task_id)
        if not task or task.status != CrawlTaskStatus.PENDING.value:
            logger.info(f'[CrawlConsumer][execute_task] 任务状态非 PENDING，跳过幂等保护: task_id={task_id}, status={getattr(task, "status", "N/A")}')
            return

        # 清除可能残留的取消标志和暂停标志，避免前一次超时通知或暂停操作影响本次执行
        await cls._clear_cancel_flag(task_id)
        await cls._clear_pause_flag(task_id)

        logger.info(f'[CrawlConsumer][execute_task] 开始执行爬取任务: task_id={task_id}')
        try:
            await cls._execute_task(task_id)
            logger.info(f'[CrawlConsumer][execute_task] 爬取任务处理完成: task_id={task_id}')
        except Exception as e:
            err = format_exception_message(e)
            # 更新任务为失败状态
            async with async_session_scope() as session:
                task = await WebCrawlerTaskDao.get_task_by_id(task_id)
                update_vo = CrawlTaskUpdateVo(
                    status=CrawlTaskStatus.FAILED.value,
                    error_code=CrawlTaskErrorCode.CONSUMER_ERROR.value,
                    error_message=err,
                    update_by=task.create_by if task else '',
                )
                await WebCrawlerTaskDao.update_task(task_id, update_vo)
                await session.commit()
            logger.error('[CrawlConsumer][execute_task] 爬取任务执行失败: task_id={}, error={}', task_id, err, exc_info=True)

    @classmethod
    async def _execute_task(cls, task_id: int) -> None:
        """
        执行爬取任务

        执行链路：标记开始 → 获取配置 → 流式爬取+逐页后处理 → 标记终态并落文档
        流式模式下每爬完一个页面立即后处理并释放 markdown 内存，避免大网站全量结果驻留内存。
        并发控制由 CrawlPipelineService 内部的 Semaphore 管理。

        事务设计说明：
        - 本方法不添加 @transactional 装饰器，作为纯编排者协调各子操作
        - 各子操作（start_task / update_task_progress / update_task_status 等）各自持有独立事务
        - 异常处理中调用 update_task_status 标记失败时，需在独立新 session 中执行，
          避免在已回滚的事务 session 内操作 DB（防止 PendingRollbackError）
        - 流式循环内的进度更新各自独立提交，避免长事务占用 DB 连接

        任务取消机制：
        - 超时兜底定时任务会发送 Redis 取消通知（不修改 DB 状态）
        - 爬取循环中每处理完一页后检查 Redis 取消标志（见 CrawlPipelineService._check_task_cancelled）
        - 发现取消标志后抛出 TaskCancelledException，由本方法捕获并设置 FAILED+TIMEOUT
        - 取消场景下本方法仍持有 crawl_task_key 分布式锁，无状态竞争

        :param task_id: 任务ID
        """
        try:
            # 步骤1-2：标记开始 + 获取配置
            task, crawl_config, target_url = await cls._prepare_task_execution(task_id)

            # 步骤2-3：获取已全链路成功的URL集合+流式爬取
            skip_urls = await WebCrawlerTaskUrlRecordDao.get_success_urls_by_task_id(task_id)

            # 步骤3-6：流式爬取 → 逐页后处理 → 分类统计 → 实时进度
            success, failed, success_results, failed_results = await cls._execute_crawl_stream(
                task_id, target_url, crawl_config, task, skip_urls,
            )

            # 步骤7：标记终态并落文档（COMPLETED / FAILED）
            await cls._finalize_crawl(task_id, target_url, success, failed, success_results, failed_results)
        except TaskCancelledException as e:
            # 任务被取消（超时兜底发送了 Redis 取消通知），自行设置失败状态
            logger.info(f'[Executor] 任务被取消: task_id={task_id}, reason={e}')
            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.FAILED.value,
                error_code=CrawlTaskErrorCode.TIMEOUT.value,
                error_message=f'任务执行超时（超过{Crawl4aiConfig.crawl4ai_task_timeout_minutes}分钟）',
            )
            # 清除取消标志
            await cls._clear_cancel_flag(task_id)
        except TaskPausedException as e:
            # 任务被暂停（用户通过 Agent 工具发送了 Redis 暂停通知）
            logger.info(f'[Executor] 任务被暂停: task_id={task_id}, reason={e}')
            # 标记为 PAUSED 状态，保留当前进度
            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.PAUSED.value,
            )
            # 清除暂停标志（通知调用方暂停已响应）
            await cls._clear_pause_flag(task_id)
        except ServiceException as e:
            err = format_exception_message(e)
            logger.exception('[Executor] 业务异常: task_id={}, error={}', task_id, err)
            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.FAILED.value,
                error_code=CrawlTaskErrorCode.BIZ_ERROR.value,
                error_message=err,
            )
        except Exception as e:
            err = format_exception_message(e)
            logger.exception('[Executor] 执行异常: task_id={}, error={}', task_id, err)
            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.FAILED.value,
                error_code=CrawlTaskErrorCode.EXEC_ERROR.value,
                error_message=err,
            )

    @classmethod
    async def _clear_cancel_flag(cls, task_id: int) -> None:
        """
        清除任务取消标志

        每次执行前清除可能残留的取消标志（如前一次超时通知的 TTL 尚未过期），
        避免旧取消标志导致本次执行被误取消。

        :param task_id: 任务ID
        """
        redis = RedisContext.get_redis()
        cancel_key = RedisKey.crawl_task_cancel_key(task_id)
        await redis.delete(cancel_key)

    @classmethod
    async def _clear_pause_flag(cls, task_id: int) -> None:
        """
        清除任务暂停标志

        每次执行前清除可能残留的暂停标志（如前一次暂停操作的 TTL 尚未过期），
        避免旧暂停标志导致本次执行被误暂停。
        暂停场景下执行器检测到暂停标志后也需主动删除以通知调用方。

        :param task_id: 任务ID
        """
        redis = RedisContext.get_redis()
        pause_key = RedisKey.crawl_task_pause_key(task_id)
        await redis.delete(pause_key)

    @classmethod
    async def _prepare_task_execution(cls, task_id: int):
        """
        准备任务执行环境

        标记任务开始 → 获取任务配置 → 解析爬取参数

        :param task_id: 任务ID
        :return: (task对象, 爬取配置字典, 目标URL)
        """
        await WebCrawlerTaskService.start_task(task_id)
        task = await WebCrawlerTaskService.get_task(task_id)
        crawl_config = json.loads(task.crawl_config) if task.crawl_config else {}
        target_url = task.target_url
        logger.info(f'[Executor] 开始执行爬取: task_id={task_id}, url={target_url}')
        return task, crawl_config, target_url

    @classmethod
    async def _execute_crawl_stream(
        cls, task_id: int, target_url: str, crawl_config: dict, task,
        skip_urls: set[str] | None = None,
    ) -> tuple[int, int, list[CrawlProcessedVo], list[CrawlProcessedVo]]:
        """
        流式爬取并逐页处理

        通过 CrawlPipelineService.stream_crawl_and_process_yield 逐条 yield，
        每爬完一页立即：分类统计 → 更新任务进度 → 保存URL记录，并收集成功/失败结果列表。

        :param task_id: 任务ID
        :param target_url: 目标URL
        :param crawl_config: 爬取配置字典
        :param task: 任务对象（用于读取 total_count 粗估值、create_by 等字段）
        :param skip_urls: 重试场景下已全链路成功的URL集合，命中的URL将跳过后处理直接标记为skipped
        :return: (成功数, 失败数, 成功结果列表, 失败结果列表)
        """
        success_results: list[CrawlProcessedVo] = []
        failed_results: list[CrawlProcessedVo] = []
        success = 0
        failed = 0

        async for vo in CrawlPipelineService.stream_crawl_and_process_yield(
            task_id=task_id, target_url=target_url,
            crawl_config=crawl_config, skip_urls=skip_urls,
        ):
            if vo.skipped:
                # 重试跳过已成功URL，计入进度和终态统计，但无需重新落库
                success += 1
                continue
            elif vo.success and vo.object_name:
                success_results.append(vo)
                success += 1
            else:
                failed_results.append(vo)
                failed += 1

            # 更新进度（上限 99%，终态由 complete_task 设为 100）
            await cls._update_task_progress(task_id, success, failed, task)

            # 保存URL记录：首次新增 / 重试按 task_id+url 更新（逐页独立事务）
            create_by = task.create_by if task else ''
            is_success = bool(vo.success and vo.object_name)
            async with async_session_scope() as session:
                await WebCrawlerTaskUrlRecordDao.upsert_by_task_url(
                    UrlRecordUpsertVo(
                        task_id=task_id,
                        url=vo.url,
                        status=(
                            CrawlUrlRecordStatus.SUCCESS.value
                            if is_success
                            else CrawlUrlRecordStatus.FAILED.value
                        ),
                        doc_key=vo.object_name if is_success else None,
                        title=vo.title or '',
                        status_code=vo.status_code if is_success else None,
                        error_code=vo.error_code if not is_success else None,
                        error_message=vo.error_message if not is_success else None,
                        create_by=create_by,
                    )
                )
                await session.commit()

        return success, failed, success_results, failed_results

    @classmethod
    async def _update_task_progress(cls, task_id: int, success: int, failed: int, task) -> None:
        """
        计算并更新任务进度（@transactional 独立事务）

        百分比基于创建时粗估的 total_count，上限 99%，终态由 complete_task 设为 100。

        :param task_id: 任务ID
        :param success: 当前成功数
        :param failed: 当前失败数
        :param task: 任务对象（用于读取 total_count 粗估值）
        """
        current_count = success + failed
        estimated_total = task.total_count or 0
        pct = min(99, int(current_count * 100 / estimated_total)) if estimated_total > 0 else 0

        await WebCrawlerTaskService.update_task_progress(
            task_id=task_id,
            progress=pct,
            current_step=f'已处理 {current_count} 个URL',
            success_count=success,
            failed_count=failed,
            # 不传 total_count，保留创建时的粗估值
        )

    @classmethod
    async def _finalize_crawl(
        cls, task_id: int, target_url: str,
        success: int, failed: int,
        success_results: list[CrawlProcessedVo],
        failed_results: list[CrawlProcessedVo],
    ) -> None:
        """
        根据执行结果标记任务终态并落文档

        - 更新 total_count 为实际爬取到的页面数（success + failed）
        - 更新 progress = 成功页面数 / 总页面数 * 100
        - 有失败记录 → 标记 FAILED（根据是否有成功页区分全部失败/部分失败）
        - 全部成功 → 标记 COMPLETED 并投递 crawl.document.pending

        :param task_id: 任务ID
        :param target_url: 目标URL
        :param success: 成功数（含重试跳过的已成功URL）
        :param failed: 失败数
        :param success_results: 成功结果列表（保留参数，当前由消费者从 URL 记录重建）
        :param failed_results: 失败结果列表
        """
        # 计算实际爬取到的页面总数和进度
        actual_total = success + failed
        progress = int(success * 100 / actual_total) if actual_total > 0 else 0

        # 更新实际页面数和进度
        await WebCrawlerTaskService.update_task_progress(
            task_id=task_id,
            progress=progress,
            total_count=actual_total,
            success_count=success,
            failed_count=failed,
        )

        if failed > 0:
            error_code = CrawlTaskErrorCode.ALL_CRAWL_FAILED.value
            if success > 0:
                error_code = CrawlTaskErrorCode.PARTIAL_CRAWL_FAILED.value
            error_details = cls._build_error_summary(failed_results)
            await WebCrawlerTaskService.update_task_status(
                task_id, CrawlTaskStatus.FAILED.value,
                error_code=error_code,
                error_message=error_details,
            )
            logger.warning(
                f'[Executor] 爬取存在失败: task_id={task_id}, '
                f'success={success}, failed={failed}, details={error_details}',
            )
            return

        # 全部成功：标记为 COMPLETED，投递文档合并消息（由 crawl_document_consumer 落库）
        await WebCrawlerTaskService.complete_task(task_id)
        await MessageStreamService.produce(
            topic=StreamTopicConfig.crawl_document_pending,
            value=CrawlDocumentPending(task_id=task_id, target_url=target_url),
            key=str(task_id),
        )
        logger.info(f'[Executor] 爬取完成，已投递文档合并消息: task_id={task_id}, success={success}')

    @classmethod
    def _build_error_summary(cls, failed_results: list[CrawlProcessedVo]) -> str:
        """
        将失败结果列表拼接为可读的错误摘要

        格式：全部 N 个URL爬取失败: url1 [CRAWL_FAILED] 连接超时; url2 [CRAWL_FAILED] HTTP 403

        :param failed_results: 失败结果列表
        :return: 错误摘要字符串
        """
        count = len(failed_results)
        if count == 0:
            return ''
        details = '; '.join(
            f'{r.url} [{r.error_code or "N/A"}] {r.error_message or "N/A"}' for r in failed_results
        )
        return f'全部 {count} 个URL爬取失败: {details}'
