"""
爬取流水线服务

负责编排流式爬取 + 逐条后处理的完整流水线：
1. 调用 Crawl4aiClient.crawl_stream 流式获取爬取结果
2. 每收到一个结果立即调用 CrawlPostProcessorService.process_single 后处理
3. 收集处理后的轻量 summaries（markdown 已置空释放内存）

业务层无需关心底层流式细节，只需调用 stream_crawl_and_process 即可。
"""
from typing import AsyncIterable

from knowledge_common.config.env import SemaphoreConfig
from knowledge_common.common.context import RedisContext
from knowledge_common.redis import DistributedSemaphore, RedisKey, SemaphoreKey
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_url_error_code_enum import CrawlUrlErrorCode
from knowledge_content.infra.crawl4ai import Crawl4aiClient
from knowledge_content.service.crawl_failure_diagnostics import format_empty_content_message
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo
from knowledge_content.service.crawl_post_processor_service import CrawlPostProcessorService

# 全局并发控制信号量（基于 Redis BLPOP 实现真正的阻塞等待）
# 从 SemaphoreConfig.semaphore_crawl_pipeline_size 读取；
# 无可用令牌时协程被 BLPOP 挂起，令牌归还后自动唤醒（零轮询）
_task_semaphore: DistributedSemaphore | None = None


class TaskCancelledException(Exception):
    """任务被取消异常（如超时兜底触发取消）"""
    pass


class TaskPausedException(Exception):
    """任务被暂停异常（用户主动暂停触发）"""
    pass


async def _get_semaphore() -> DistributedSemaphore:
    """
    获取全局信号量（懒初始化）

    首次调用时创建信号量实例并初始化 Redis 令牌池，
    create_pool 内部使用 SET NX 保证多 worker 下仅执行一次。

    :return: 全局共享的 DistributedSemaphore 实例，限制并发爬取任务数（从配置读取）
    """
    global _task_semaphore
    if _task_semaphore is None:
        max_concurrent = SemaphoreConfig.semaphore_crawl_pipeline_size
        key = SemaphoreKey.crawl_pipeline_key()
        await DistributedSemaphore.create_pool(key=key, size=max_concurrent)
        _task_semaphore = DistributedSemaphore(key=key)
    return _task_semaphore


def _is_empty_markdown(markdown: str | None) -> bool:
    """爬取正文为空（含仅空白/换行）"""
    return not markdown or not markdown.strip()


def _empty_content_processed(result, *, requested_url: str) -> CrawlProcessedVo:
    """爬取引擎标成功但正文为空 → 结构化诊断写入 error_message。"""
    markdown = result.markdown or ''
    return CrawlProcessedVo(
        success=False,
        url=result.url,
        title=result.title,
        status_code=result.status_code,
        error_code=CrawlUrlErrorCode.EMPTY_CONTENT.value,
        error_message=format_empty_content_message(
            content_length=len(markdown),
            html_length=result.html_length,
            status_code=result.status_code,
            redirected_url=result.redirected_url,
            title=result.title,
            markdown=markdown,
            requested_url=requested_url,
            final_url=result.url,
        ),
    )

class CrawlPipelineService:
    """
    爬取流水线服务

    将流式爬取与后处理编排为单一流水线，每爬完一页立即处理并释放 markdown 内存。
    属于「爬取处理」范畴，与任务生命周期管理（执行器）职责分离。
    """
    @classmethod
    async def stream_crawl_and_process(
        cls, task_id: int, target_url: str, crawl_config: dict
    ) -> list[CrawlProcessedVo]:
        """
        流式爬取 + 逐条后处理流水线

        每爬完一个页面立即 yield → 立即后处理(图片+MinIO) → 释放 markdown 内存，
        避免大网站全量结果驻留内存。

        :param task_id: 任务ID，用于构造 MinIO 路径
        :param target_url: 目标 URL
        :param crawl_config: 爬取策略配置
        :return: 后处理完成的 CrawlProcessedVo 列表（不包含原始 markdown/media/links）
        """

        semaphore = await _get_semaphore()
        # 阻塞等待可用令牌（BLPOP 挂起协程，令牌归还后自动唤醒）
        async with semaphore:
            return await cls._stream_crawl_and_process(task_id, target_url, crawl_config)

    @classmethod
    async def _stream_crawl_and_process(
        cls, task_id: int, target_url: str, crawl_config: dict
    ) -> list[CrawlProcessedVo]:
        summaries: list[CrawlProcessedVo] = []

        logger.info(
            f'[CrawlPipeline] 开始流式爬取流水线: task_id={task_id}, url={target_url}'
        )

        async for result in Crawl4aiClient.crawl_stream(target_url, crawl_config):
            # 检查任务是否被取消或暂停
            await cls._check_task_cancelled(task_id)
            await cls._check_task_paused(task_id)

            # 失败 / 空正文：透传失败，不走后处理
            if not result.success:
                summaries.append(CrawlProcessedVo(
                    success=False,
                    url=result.url,
                    title=result.title,
                    status_code=result.status_code,
                    error_code=result.error_code,
                    error_message=result.error_message,
                ))
                continue
            if _is_empty_markdown(result.markdown):
                summaries.append(_empty_content_processed(result, requested_url=target_url))
                continue

            processed = await CrawlPostProcessorService.process_single(task_id, result)
            summaries.append(processed)

        logger.info(
            f'[CrawlPipeline] 流水线完成: task_id={task_id}, results={len(summaries)}'
        )
        return summaries

    @classmethod
    async def stream_crawl_and_process_yield(
            cls, task_id: int, target_url: str, crawl_config: dict,
            skip_urls: set[str] | None = None,
    ) -> AsyncIterable[CrawlProcessedVo]:
        """
        流式爬取 + 逐条后处理流水线（yield 版本）

        与 stream_crawl_and_process 区别：不收集全量结果列表，每页完成后立即 yield，
        调用方可逐条处理并实时更新进度。

        :param task_id: 任务ID，用于构造 MinIO 路径
        :param target_url: 目标 URL
        :param crawl_config: 爬取策略配置
        :param skip_urls: 重试场景下已全链路成功的URL集合，命中的URL将跳过后处理直接标记为skipped
        :return: 逐条 yield 后处理完成的 CrawlProcessedVo
        """

        semaphore = await _get_semaphore()
        async with semaphore:
            async for item in cls._stream_crawl_and_process_yield(
                task_id, target_url, crawl_config, skip_urls=skip_urls,
            ):
                yield item

    @classmethod
    async def _stream_crawl_and_process_yield(
            cls, task_id: int, target_url: str, crawl_config: dict,
            skip_urls: set[str] | None = None,
    ) -> AsyncIterable[CrawlProcessedVo]:
        count = 0
        logger.info(
            f'[CrawlPipeline] 开始流式爬取流水线: task_id={task_id}, url={target_url}'
        )

        async for result in Crawl4aiClient.crawl_stream(target_url, crawl_config):
            count += 1

            # 检查任务是否被取消或暂停
            await cls._check_task_cancelled(task_id)
            await cls._check_task_paused(task_id)

            # 重试场景：该URL已在上次执行中全链路成功，跳过后处理直接标记为skipped
            if skip_urls and result.url in skip_urls:
                logger.debug(f'[CrawlPipeline] 跳过已成功URL: task_id={task_id}, url={result.url}')
                yield CrawlProcessedVo(success=True, url=result.url, skipped=True)
                continue

            # 失败 / 空正文：透传失败，不走后处理
            if not result.success:
                yield CrawlProcessedVo(
                    success=False,
                    url=result.url,
                    title=result.title,
                    status_code=result.status_code,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
                continue
            if _is_empty_markdown(result.markdown):
                yield _empty_content_processed(result, requested_url=target_url)
                continue

            processed = await CrawlPostProcessorService.process_single(task_id, result)
            yield processed

        logger.info(
            f'[CrawlPipeline] 流水线完成: task_id={task_id}, results={count}'
        )

    @classmethod
    async def _check_task_cancelled(cls, task_id: int) -> None:
        """
        检查任务是否被取消

        通过检查 Redis 中的取消标志判断任务是否已被取消（如超时兜底触发）。
        如果标志存在，抛出 TaskCancelledException 以停止爬取流程。

        :param task_id: 任务ID
        :raises TaskCancelledException: 任务已被取消
        """
        redis = RedisContext.get_redis()
        cancel_key = RedisKey.crawl_task_cancel_key(task_id)
        is_cancelled = await redis.exists(cancel_key)
        if is_cancelled:
            logger.warning(f'[CrawlPipeline] 任务已被取消: task_id={task_id}')
            raise TaskCancelledException(f'任务 {task_id} 已被取消')

    @classmethod
    async def _check_task_paused(cls, task_id: int) -> None:
        """
        检查任务是否被暂停

        通过检查 Redis 中的暂停标志判断任务是否已被用户主动暂停。
        如果标志存在，抛出 TaskPausedException 以停止爬取流程。

        :param task_id: 任务ID
        :raises TaskPausedException: 任务已被暂停
        """
        redis = RedisContext.get_redis()
        pause_key = RedisKey.crawl_task_pause_key(task_id)
        is_paused = await redis.exists(pause_key)
        if is_paused:
            logger.warning(f'[CrawlPipeline] 任务已被暂停: task_id={task_id}')
            raise TaskPausedException(f'任务 {task_id} 已被暂停')
