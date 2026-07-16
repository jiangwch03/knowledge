"""
crawl_merge_results 合并已爬内容工具

放弃失败的URL，将已成功爬取的页面提交到文档合并队列（异步落库）。
供 LLM 在用户明确要求「跳过爬取直接合并」时调用。
"""

from langchain_core.tools import tool

from knowledge_common.common import with_session
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
@with_session
async def merge_crawl_results(task_id: int | None = None) -> str:
    """
    提交合并已爬内容：放弃失败的URL，将已成功爬取的页面投入文档合并队列。

    本工具仅表示「合并请求已提交」，不会同步等待知识库文档生成。
    任务状态会先变为 COMPLETED（已完成/待合并），消费者落库成功后才会变为 CONVERTED（已转换）。
    请勿把「提交成功」表述成「已合入知识库」。

    当爬取任务虽然部分页面失败但有成功爬取的页面时，
    用户要求「跳过爬取直接合并」或「放弃失败的页面，把已有的内容保存」时使用此工具。
    适用于 FAILED / USER_DECISION / PAUSED / CONVERT_FAILED 状态的任务。

    Args:
        task_id: 任务 ID（必填）
    """
    if task_id is None:
        logger.error('[MergeTask] 缺少 task_id')
        return '缺少任务 ID，请传入 task_id'

    try:
        logger.info('[MergeTask] 开始提交合并已爬内容: task_id={}', task_id)
        result = await WebCrawlerTaskService.merge_crawl_results(task_id)
        logger.info('[MergeTask] 合并已提交: task_id={}, msg={}', task_id, result)
        return result

    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[MergeTask] 合并提交异常: task_id={}, error={}', task_id, err)
        return f'合并提交失败: {err}'
