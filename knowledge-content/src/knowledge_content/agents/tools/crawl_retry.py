"""
crawl_retry 爬取失败重试工具

失败分析后调整爬取参数，通过该工具重置任务状态为 PENDING 后重新执行。
支持在重试时传入新爬取策略配置与可选的新目标 URL；提交组合须先对本会话试爬成功。

与 crawl_execute 的区别：
- crawl_execute: 创建全新爬取任务
- crawl_retry: 复用已有失败任务，重置状态后重试，可同时更新爬取参数 / 目标入口

注意：
- task_id 需由 LLM 显式传入
- 入口变更时须传入 target_url（与用户确认的新入口一致）
- 更新者从 runtime.context.user_name 获取
"""

import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.crawl_submit_gate import (
    CrawlSubmitPrepared,
    prepare_crawl_submit,
)
from knowledge_content.agents.utils.failed_url_samples import resolve_failed_url_samples
from knowledge_content.agents.utils.strategy_config_util import CrawlConfigArg
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
async def crawl_retry(
    crawl_config: CrawlConfigArg = None,
    task_id: int | None = None,
    target_url: str | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """
    重试已失败的爬取任务，返回任务状态摘要 JSON。

    当爬取任务失败后，须经规划助手分析并调整爬取参数，再调用此工具重置任务状态后重新执行。
    禁止原配置直接重试；crawl_config 须为规划助手诊断后的策略 JSON 字符串。
    若诊断后改用新入口（如 SEED_SCOPE_MISMATCH 建议入口），须同时传入 target_url；
    未传则沿用任务原有目标 URL。
    提交前会校验：若有失败 URL，须对本任务「任意一个」失败页 + 新 crawl_config
    试爬成功（第 1 个或第 N 个都行；禁止仅用任务入口页冒充；不要求修通全部失败页）；
    入口变更时还须对新入口试爬成功。
    重试后任务状态变为 PENDING；用户询问进度时再调用 query_crawl_task。
    重试使用原有 task_id，不会创建新任务。

    返回包含以下信息的 JSON 字符串：
    - success: 是否成功提交重试
    - task_id: 任务 ID
    - status: 重试后的任务状态
    - retry_count: 累计重试次数
    - max_retry_count: 当前规则自动重试上限（本次人工重试会 += crawl4ai_rule_retry_limit）
    - url: 本次生效的目标 URL
    - summary: 简要结果描述

    Args:
        crawl_config: 规划助手调整后的完整爬取策略配置 JSON 字符串（必填）
        task_id: 任务 ID（必填）
        target_url: 可选；入口变更时传入用户确认的新起点 URL，未传则沿用任务原 URL
    """
    if task_id is None:
        logger.error('[CrawlRetry] 缺少 task_id')
        return json.dumps({
            'success': False,
            'task_id': None,
            'status': 'failed',
            'summary': '缺少任务 ID，请传入 task_id',
            'message': '缺少任务 ID，请传入 task_id',
        }, ensure_ascii=False)

    try:
        task = await WebCrawlerTaskService.get_task(task_id)
        failed_samples = await resolve_failed_url_samples(
            task_id,
            error_message=getattr(task, 'error_message', None),
        )
        explicit_target = (target_url or '').strip()
        entry_changed = bool(
            explicit_target and explicit_target != (task.target_url or '').strip()
        )
        # 有失败样本：强制样本试爬；入口未改时不强制入口页凭证（避免冒充验证）
        also_require_target = entry_changed or not failed_samples
        prepared = await prepare_crawl_submit(
            runtime=runtime,
            crawl_config_arg=crawl_config,
            target_url=target_url,
            fallback_url=task.target_url,
            task_id=task_id,
            require_nonempty_config=True,
            log_tag='CrawlRetry',
            action_hint='再重试',
            require_trial_urls=failed_samples or None,
            also_require_target_trial=also_require_target,
        )
        if not isinstance(prepared, CrawlSubmitPrepared):
            return prepared

        logger.info(
            '[CrawlRetry] 重试爬取任务: task_id={}, url={}, update_by={}',
            task_id, prepared.target_url, prepared.identity.user_name,
        )

        result = await WebCrawlerTaskService.retry_task(
            task_id,
            crawl_config=prepared.crawl_config,
            target_url=prepared.target_url,
            update_by=prepared.identity.user_name,
            extend_max_retry=True,
        )

        # 独立事务已提交；勿依赖外层 session identity map 读旧实体
        status = result['status']
        retry_count = result['retry_count']
        max_retry_count = result['max_retry_count']
        effective_url = result['target_url']
        logger.info(
            '[CrawlRetry] 任务已重试: task_id={}, retry_count={}/{}, status={}, url={}',
            task_id, retry_count, max_retry_count, status, effective_url,
        )
        return json.dumps({
            'success': True,
            'task_id': task_id,
            'status': status,
            'retry_count': retry_count,
            'max_retry_count': max_retry_count,
            'url': effective_url,
            'summary': (
                f'爬取任务已重试（ID={task_id}），状态={status}，'
                f'累计重试 {retry_count}/{max_retry_count} 次，目标 URL={effective_url}'
            ),
        }, ensure_ascii=False)

    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[CrawlRetry] 重试任务异常: task_id={}, error={}', task_id, err)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'status': 'failed',
            'summary': f'重试爬取任务失败: {err}',
            'message': f'重试爬取任务失败: {err}',
        }, ensure_ascii=False)
