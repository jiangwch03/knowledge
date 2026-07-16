"""
persist_crawl_results 入库已爬内容工具

放弃失败的 URL，将已成功爬取的页面提交到文档落库队列（异步写主表+文件子表）。
供 LLM 在用户明确要求「跳过失败直接入库」时调用。

兼容旧名 merge_crawl_results（同函数对象）。
"""

from langchain_core.tools import tool

from knowledge_common.common import with_session
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
@with_session
async def persist_crawl_results(task_id: int | None = None) -> str:
    """
    提交入库已爬内容：放弃失败的URL，将已成功爬取的页面投入文档落库队列。

    本工具仅表示「入库请求已提交」，不会同步等待知识库文档生成。
    任务状态会先变为 COMPLETED（已完成/待落库），消费者落库成功后才会变为 CONVERTED（已转换）。
    请勿把「提交成功」表述成「已合入知识库」。

    当爬取任务虽然部分页面失败但有成功爬取的页面时，
    用户要求「跳过失败直接入库」或「放弃失败的页面，把已有的内容保存」时使用此工具。
    适用于 FAILED / USER_DECISION / PAUSED / CONVERT_FAILED 状态的任务。

    Args:
        task_id: 任务 ID（必填）
    """
    if task_id is None:
        logger.error('[PersistTask] 缺少 task_id')
        return '缺少任务 ID，请传入 task_id'

    try:
        logger.info('[PersistTask] 开始提交入库已爬内容: task_id={}', task_id)
        result = await WebCrawlerTaskService.persist_crawl_results(task_id)
        logger.info('[PersistTask] 入库已提交: task_id={}, msg={}', task_id, result)
        return result

    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[PersistTask] 入库提交异常: task_id={}, error={}', task_id, err)
        return f'入库提交失败: {err}'


# 旧名兼容（checkpoint / 旧 prompt 可能仍引用）
merge_crawl_results = persist_crawl_results
