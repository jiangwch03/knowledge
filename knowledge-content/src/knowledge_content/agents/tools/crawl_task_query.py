"""
query_crawl_task 爬取任务详情/进度查询工具

- 按 task_id：查详情并校验数据权限
- 按 target_url：防重复爬取检查，仅返回当前用户可见范围内是否已有任务
"""

import json

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import ServiceException, format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import (
    WebCrawlerTaskUrlRecordDao,
)
from knowledge_content.mapper.do.web_crawler_task_do import WebCrawlerTask
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService

_STATUS_LABELS = {status.value: status.label for status in CrawlTaskStatus}
# 塞进工具返回给 LLM；过多会撑上下文，门禁仍用全量失败 URL
_FAILED_URL_DETAIL_LIMIT = 20


async def _load_failed_url_details(task_id: int) -> list[dict]:
    """从 URL 记录表组装失败页明细（含 error_code / error_message 诊断文案）。"""
    records = await WebCrawlerTaskUrlRecordDao.get_failed_records_by_task_id(task_id)
    details: list[dict] = []
    for record in records[:_FAILED_URL_DETAIL_LIMIT]:
        url = (getattr(record, 'url', None) or '').strip()
        if not url:
            continue
        details.append({
            'url': url,
            'error_code': (getattr(record, 'error_code', None) or '').strip() or None,
            'error_message': (getattr(record, 'error_message', None) or '').strip() or None,
            'status_code': getattr(record, 'status_code', None),
            'title': (getattr(record, 'title', None) or '').strip() or None,
        })
    return details


@tool
async def query_crawl_task(
    task_id: int | None = None,
    target_url: str | None = None,
) -> str:
    """
    查询后台爬取任务。

    两种查询语义不同：
    - task_id：查任务详情，校验当前用户数据权限（accessible）
    - target_url：防重复爬取，查当前用户可见范围内是否已有该网址任务（found，不涉及权限字段）

    返回 JSON 均含 query_by（task_id / target_url）。
    失败任务额外返回 failed_url_details（url / error_code / error_message / status_code），
    供分析 EMPTY_CONTENT 等失败原因并调参，勿只看拼接后的 error_message。

    Args:
        task_id: 任务 ID（与 target_url 二选一，同时传入时优先 task_id）
        target_url: 爬取目标 URL（查该 URL 下最新版本任务，仅用于防重复）
    """
    if task_id is None and not target_url:
        logger.error('[QueryTask] 缺少 task_id 或 target_url')
        return json.dumps({
            'success': False,
            'query_by': None,
            'summary': '请传入 task_id 或 target_url 之一',
        }, ensure_ascii=False)

    if task_id is not None:
        return await _query_crawl_task_by_id(task_id)
    return await _query_crawl_task_by_url(target_url.strip())  # type: ignore[union-attr]


async def _query_crawl_task_by_id(task_id: int) -> str:
    logger.info('[QueryTask] 按 task_id 查询任务详情: task_id={}', task_id)
    try:
        task = await WebCrawlerTaskService.get_task_with_data_scope(task_id)
        return await _format_task_found(task, query_by='task_id')
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[QueryTask] task_id 查询异常: task_id={}, error={}', task_id, err)
        return json.dumps({
            'success': False,
            'query_by': 'task_id',
            'accessible': False,
            'task_id': task_id,
            'summary': err if isinstance(e, ServiceException) else f'查询任务状态失败: {err}',
        }, ensure_ascii=False)


async def _query_crawl_task_by_url(target_url: str) -> str:
    logger.info('[QueryTask] 按 target_url 防重复检查: url={}', target_url)
    if not target_url:
        return json.dumps({
            'success': False,
            'query_by': 'target_url',
            'found': False,
            'target_url': target_url,
            'summary': 'URL 不能为空',
        }, ensure_ascii=False)

    try:
        task = await WebCrawlerTaskService.find_latest_visible_task_by_url(target_url)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[QueryTask] target_url 查询异常: url={}, error={}', target_url, err)
        return json.dumps({
            'success': False,
            'query_by': 'target_url',
            'found': False,
            'target_url': target_url,
            'summary': err if isinstance(e, ServiceException) else f'查询任务状态失败: {err}',
        }, ensure_ascii=False)

    if task is None:
        logger.info('[QueryTask] target_url 未匹配到可见任务: url={}', target_url)
        return json.dumps({
            'success': True,
            'query_by': 'target_url',
            'found': False,
            'target_url': target_url,
            'summary': '该网址下未发现可见的爬取任务，可按新站出方案',
        }, ensure_ascii=False)

    return await _format_task_found(task, query_by='target_url')


async def _format_task_found(task: WebCrawlerTask, query_by: str) -> str:
    crawl_config = json.loads(task.crawl_config) if task.crawl_config else {}
    terminal_statuses = {
        CrawlTaskStatus.COMPLETED.value,
        CrawlTaskStatus.CONVERTED.value,
        CrawlTaskStatus.FAILED.value,
        CrawlTaskStatus.CONVERT_FAILED.value,
    }
    is_terminal = task.status in terminal_statuses
    status_label = _STATUS_LABELS.get(task.status, task.status)

    summary_lines = []
    if query_by == 'target_url':
        summary_lines.append(f'已匹配 URL 下最新版本任务（版本 {task.doc_version or "未知"}）')
    if task.status == CrawlTaskStatus.PENDING.value:
        summary_lines.append('任务已提交，等待执行')
    elif task.status == CrawlTaskStatus.RUNNING.value:
        summary_lines.append(f'任务正在执行: {task.current_step or "爬取中"}')
    elif task.status == CrawlTaskStatus.PAUSED.value:
        summary_lines.append('任务已暂停')
    elif task.status == CrawlTaskStatus.COMPLETED.value:
        summary_lines.append(f'爬取完成，共 {task.total_count or 0} 页')
    elif task.status == CrawlTaskStatus.CONVERTED.value:
        summary_lines.append('爬取完成并已落库')
    elif task.status == CrawlTaskStatus.FAILED.value:
        summary_lines.append('任务失败自动重试爬取中暂时不需要介入')
    elif task.status == CrawlTaskStatus.CONVERT_FAILED.value:
        summary_lines.append('MD合并失败，系统自动重试中；久未恢复请联系运维')
    elif task.status == CrawlTaskStatus.USER_DECISION.value:
        summary_lines.append('多次重试尝试爬取失败,失败网址异常信息如下:')
        if task.error_message:
            summary_lines.append(task.error_message)

    failed_url_details: list[dict] = []
    failed_count = int(task.failed_count or 0)
    if failed_count > 0 or task.status in {
        CrawlTaskStatus.FAILED.value,
        CrawlTaskStatus.USER_DECISION.value,
    }:
        try:
            failed_url_details = await _load_failed_url_details(task.task_id)
        except Exception as e:
            logger.exception(
                '[QueryTask] 加载失败 URL 明细异常: task_id={}, error={}',
                task.task_id, format_exception_message(e),
            )

    if failed_url_details and task.status == CrawlTaskStatus.USER_DECISION.value:
        # 明细优先于可能过时的任务级摘要，便于观察环节直接读诊断
        detail_lines = [
            f'{d["url"]} [{d.get("error_code") or "N/A"}] {d.get("error_message") or "N/A"}'
            for d in failed_url_details[:5]
        ]
        summary_lines.append('失败页明细: ' + '; '.join(detail_lines))

    result: dict = {
        'success': True,
        'query_by': query_by,
        'task_id': task.task_id,
        'doc_version': task.doc_version,
        'target_url': task.target_url,
        'status': task.status,
        'status_label': status_label,
        'progress': task.progress,
        'current_step': task.current_step,
        'success_count': task.success_count,
        'failed_count': task.failed_count,
        'total_count': task.total_count,
        'error_code': task.error_code,
        'error_message': task.error_message,
        'failed_url_details': failed_url_details,
        'crawl_config': crawl_config,
        'is_terminal': is_terminal,
        'summary': '; '.join(summary_lines),
    }
    if query_by == 'task_id':
        result['accessible'] = True
    else:
        result['found'] = True

    logger.info(
        '[QueryTask] 结果: query_by={}, task_id={}, status={}, doc_version={}, progress={}, '
        'terminal={}, failed_details={}',
        query_by, task.task_id, task.status, task.doc_version, task.progress, is_terminal,
        len(failed_url_details),
    )
    return json.dumps(result, ensure_ascii=False)
