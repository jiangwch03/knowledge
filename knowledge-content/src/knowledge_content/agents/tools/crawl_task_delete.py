"""
crawl_task_delete 爬取任务删除工具

删除指定的后台爬取任务（软删除）。
供 LLM 在用户明确要求删除任务时调用。
"""

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
async def delete_crawl_task(task_id: int | None = None) -> str:
    """
    删除指定的爬取任务（软删除）。

    当用户明确要求放弃/删除某个爬取任务时使用此工具。
    删除后任务将不再显示。

    Args:
        task_id: 任务 ID（必填）
    """
    if task_id is None:
        logger.error('[DeleteTask] 缺少 task_id')
        return '缺少任务 ID，请传入 task_id'

    try:
        logger.info('[DeleteTask] 删除任务: task_id={}', task_id)

        await WebCrawlerTaskService.delete_task(task_id)

        logger.info('[DeleteTask] 删除成功: task_id={}', task_id)
        return f'任务 {task_id} 已删除'

    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[DeleteTask] 删除异常: task_id={}, error={}', task_id, err)
        return f'删除任务失败: {err}'
