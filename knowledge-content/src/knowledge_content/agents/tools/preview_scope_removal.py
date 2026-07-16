"""
preview_scope_removal — 预览改范围待删 URL 清单

根据任务已爬 SUCCESS 页面与新 crawl_config 中的范围过滤规则，
计算 rescope 后需删除的 URL 列表；无法解析范围规则时视为无需删页。
"""

import json

from langchain_core.tools import tool

from knowledge_common.common import with_session
from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.strategy_config_util import (
    CrawlConfigArgRequired,
    parse_tool_crawl_config,
)
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
@with_session
async def preview_scope_removal(
    crawl_config: CrawlConfigArgRequired,
    task_id: int | None = None,
) -> str:
    """
    预览应用新爬取范围后需删除的已爬 URL 清单。

    在爬取中途改范围、规划助手已产出新 crawl_config 后调用。
    工具会查询任务已成功爬取的 URL，按新策略中的范围规则计算不再匹配的页面；
    若配置中解析不到范围规则，则返回空列表（无需删页）。
    向用户展示结果并确认后，再将 urls_to_remove 传入「应用新范围」。

    返回 JSON 字段：
    - success: 是否成功
    - task_id: 任务 ID
    - pages_to_remove: 待删页面列表，每项含 url、title、reason
    - urls_to_remove: 待删 URL 字符串列表（可直接用于应用新范围）
    - removed_count: 待删数量
    - crawled_success_count: 当前已成功爬取页数（无范围规则时为 0）
    - summary: 中文摘要

    Args:
        task_id: 任务 ID（必填）
        crawl_config: 规划助手确认后的新 crawl4ai 策略 JSON 字符串（原样传入即可）
    """
    if task_id is None:
        return json.dumps({
            'success': False,
            'task_id': None,
            'summary': '缺少 task_id，请传入任务 ID',
        }, ensure_ascii=False)

    try:
        parsed_config = parse_tool_crawl_config(crawl_config)
    except ValueError as e:
        logger.exception('[PreviewScopeRemoval] crawl_config 解析失败: {}', e)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'summary': f'crawl_config 解析失败: {e}',
        }, ensure_ascii=False)

    if not parsed_config:
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'summary': '缺少 crawl_config，请传入规划助手产出的新爬取配置',
        }, ensure_ascii=False)

    try:
        result = await WebCrawlerTaskService.preview_scope_removal(task_id, parsed_config)
        logger.info(
            '[PreviewScopeRemoval] task_id={}, removed_count={}, crawled_success_count={}',
            task_id, result.get('removed_count'), result.get('crawled_success_count'),
        )
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[PreviewScopeRemoval] task_id={}, error={}', task_id, err)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'summary': err if isinstance(e, ServiceException) else f'计算删页清单失败: {err}',
        }, ensure_ascii=False)
