"""
list_actionable_crawl_tasks — 查询可操作的爬取任务列表

按用户数据权限返回 RUNNING / PAUSED / USER_DECISION / FAILED 状态任务，
供用户选择要暂停、恢复、重试或调整范围的目标任务。
"""

import json

from langchain_core.tools import tool

from knowledge_common.common import with_session
from knowledge_common.common.vo import PageModel
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.do.web_crawler_task_do import WebCrawlerTask
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService

_STATUS_LABELS = {status.value: status.label for status in CrawlTaskStatus}


@tool
@with_session
async def list_actionable_crawl_tasks(
    page_num: int = 1,
    page_size: int = 20,
) -> str:
    """
    查询当前用户有权操作的爬取任务列表。

    当用户未提供 task_id、或需要选择要操作哪个任务时调用。
    仅返回执行中(RUNNING)、已暂停(PAUSED)、待决策(USER_DECISION)、失败(FAILED) 的任务。

    返回 JSON，包含：
    - tasks: 当前页任务列表，每项字段：
        - task_id: 任务 ID，后续暂停/恢复/重试等操作须传入此 ID
        - target_url: 爬取目标网址
        - doc_version: 文档版本号
        - status: 任务状态码（RUNNING / PAUSED / USER_DECISION / FAILED）
        - status_label: 状态中文描述（如「执行中」「已暂停」）
    - page_num: 当前页码
    - page_size: 每页条数
    - total: 符合条件的总条目数
    - has_next: 是否有下一页
    - summary: 分页摘要，含总条数与翻页提示

    Args:
        page_num: 页码，默认 1
        page_size: 每页条数，默认 20，最大 50
    """
    page_num = max(page_num, 1)
    page_size = min(max(page_size, 1), 50)

    try:
        result = await WebCrawlerTaskService.list_actionable_tasks(
            page_num=page_num,
            page_size=page_size,
        )
        return _format_task_list_result(result, page_num=page_num, page_size=page_size)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[ListActionableTasks] 查询异常: {}', err)
        return json.dumps({
            'success': False,
            'tasks': [],
            'page_num': page_num,
            'page_size': page_size,
            'total': 0,
            'has_next': False,
            'summary': f'查询可操作任务失败: {err}',
        }, ensure_ascii=False)


def _format_task_list_result(
    result: PageModel | list[WebCrawlerTask],
    page_num: int,
    page_size: int,
) -> str:
    if isinstance(result, PageModel):
        rows = result.rows or []
        total = result.total
        has_next = result.has_next
        page_num = result.page_num or page_num
        page_size = result.page_size or page_size
    else:
        rows = result
        total = len(rows)
        has_next = False

    tasks = [
        {
            'task_id': task.task_id,
            'target_url': task.target_url,
            'doc_version': task.doc_version,
            'status': task.status,
            'status_label': _STATUS_LABELS.get(task.status, task.status),
        }
        for task in rows
    ]

    if total == 0:
        summary = '当前没有可操作的爬取任务'
    else:
        start = (page_num - 1) * page_size + 1
        end = min(page_num * page_size, total)
        summary = f'共 {total} 个可操作任务，当前第 {page_num} 页（{start}-{end}）'
        if has_next:
            summary += f'，可传 page_num={page_num + 1} 查看下一页'

    logger.info(
        '[ListActionableTasks] total={}, page_num={}, page_size={}, returned={}',
        total, page_num, page_size, len(tasks),
    )
    return json.dumps({
        'success': True,
        'tasks': tasks,
        'page_num': page_num,
        'page_size': page_size,
        'total': total,
        'has_next': has_next,
        'summary': summary,
    }, ensure_ascii=False)
