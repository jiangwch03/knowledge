"""
apply_scope_change — 爬取中途调整范围（Supervisor 工具）

PAUSED 下：删页 + 更新 crawl_config（可改目标入口）+ resume（不增加 retry_count）。
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
from knowledge_content.agents.utils.strategy_config_util import CrawlConfigArgRequired
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
async def apply_scope_change(
    crawl_config: CrawlConfigArgRequired,
    task_id: int,
    urls_to_remove: list[str] | None = None,
    target_url: str | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """
    在任务 PAUSED 状态下应用新的爬取范围：更新 crawl_config，可选更新目标入口与删除越界 URL，然后恢复爬取。

    与 resume_crawl_task 的区别：本工具会修改 crawl_config，并可能删除已爬 URL 记录、更新 target_url。
    与 crawl_retry 的区别：本工具不增加 retry_count，语义为中途 rescope 而非失败重试。
    若改用新入口，须传入 target_url；未传则沿用任务原有目标 URL。
    提交前会校验：本会话已对「生效 target_url + 新 crawl_config」试爬成功。
    提交后异步执行，用户询问进度时再 query_crawl_task。

    Args:
        task_id: 任务 ID（必填）
        crawl_config: 用户确认后的新 crawl4ai 策略 JSON 字符串
        urls_to_remove: 用户确认后需删除的 URL 列表；扩范围时显式传 []
        target_url: 可选；入口变更时传入用户确认的新起点 URL，未传则沿用任务原 URL
    """
    if task_id is None:
        return json.dumps({
            'success': False,
            'message': '缺少 task_id，请传入 task_id',
            'summary': '缺少 task_id，请传入 task_id',
        }, ensure_ascii=False)

    if urls_to_remove is None:
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'message': '缺少 urls_to_remove，请显式传入列表；扩范围请传 []',
            'summary': '缺少 urls_to_remove，请显式传入列表；扩范围请传 []',
        }, ensure_ascii=False)

    try:
        task = await WebCrawlerTaskService.get_task_with_data_scope(task_id)
        prepared = await prepare_crawl_submit(
            runtime=runtime,
            crawl_config_arg=crawl_config,
            target_url=target_url,
            fallback_url=task.target_url,
            task_id=task_id,
            require_nonempty_config=True,
            log_tag='ApplyScopeChange',
            action_hint='再应用新范围',
        )
        if not isinstance(prepared, CrawlSubmitPrepared):
            return prepared

        return await _apply_scope_change(
            task_id,
            prepared.crawl_config,
            urls_to_remove,
            target_url=prepared.target_url,
            update_by=prepared.identity.user_name,
        )
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[ApplyScopeChange] task_id={}, error={}', task_id, err)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'message': err,
            'summary': err,
        }, ensure_ascii=False)


def _normalize_urls_to_remove(urls_to_remove: list[str] | None) -> list[str]:
    """清洗并去重工具入参中的待删 URL 列表。"""
    urls = [u for u in (urls_to_remove or []) if u]
    return list(dict.fromkeys(urls))


async def _apply_scope_change(
    task_id: int,
    crawl_config: dict,
    urls_to_remove: list[str] | None = None,
    target_url: str | None = None,
    update_by: str = '',
) -> str:
    remove_urls = _normalize_urls_to_remove(urls_to_remove)

    result = await WebCrawlerTaskService.apply_scope_change(
        task_id,
        crawl_config,
        urls_to_remove=remove_urls or None,
        target_url=target_url,
        update_by=update_by,
    )
    removed_count = result.get('removed_count', 0)

    summary = (
        f'范围已更新（删除 {removed_count} 条 URL 记录），任务 {task_id} 将异步继续爬取'
        if removed_count
        else f'范围已更新，任务 {task_id} 将异步继续爬取'
    )
    if target_url:
        summary = f'{summary}；目标 URL={target_url}'

    logger.info(
        '[ApplyScopeChange] 已提交: task_id={}, removed_count={}, url={}',
        task_id, removed_count, target_url,
    )
    return json.dumps({
        'success': True,
        'task_id': task_id,
        'url': target_url,
        'summary': summary,
        'message': summary,
    }, ensure_ascii=False)
