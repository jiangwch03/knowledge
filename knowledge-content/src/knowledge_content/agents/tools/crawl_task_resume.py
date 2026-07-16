"""
resume_crawl_task 爬取任务恢复工具

恢复已被暂停的后台爬取任务。
供 LLM 在用户要求恢复爬取时调用。
"""

import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from knowledge_common.agent.schema.context import get_agent_identity_from_tool_runtime
from knowledge_common.common import with_session
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
@with_session
async def resume_crawl_task(
    task_id: int | None = None,
    runtime: ToolRuntime = None,
) -> str:
    """
    恢复已暂停的爬取任务。

    当用户要求恢复某一已暂停的爬取任务时使用此工具。
    只允许恢复 PAUSED 状态的任务；提交后异步执行，用户询问进度时再 query_crawl_task。

    Args:
        task_id: 任务 ID（必填）
    """
    if task_id is None:
        logger.error('[ResumeTask] 缺少 task_id')
        return json.dumps({
            'success': False,
            'task_id': None,
            'summary': '缺少任务 ID，请传入 task_id',
        }, ensure_ascii=False)

    try:
        identity = get_agent_identity_from_tool_runtime(runtime)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[ResumeTask] 身份上下文非法: {}', err)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'summary': f'系统错误：身份上下文非法: {err}',
        }, ensure_ascii=False)

    try:
        return await _resume_crawl_task(task_id, update_by=identity.user_name)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[ResumeTask] 恢复异常: task_id={}, error={}', task_id, err)
        return json.dumps({
            'success': False,
            'task_id': task_id,
            'summary': f'恢复任务失败: {err}',
        }, ensure_ascii=False)


async def _resume_crawl_task(task_id: int, update_by: str) -> str:
    """
    执行恢复操作：通过 Service 校验并发布消息，异步等待执行器接管。

    :param task_id: 爬取任务 ID
    :param update_by: 更新者（登录名）
    :return: JSON 格式结果
    """
    logger.info('[ResumeTask] 开始恢复任务: task_id={}, update_by={}', task_id, update_by)

    await WebCrawlerTaskService.resume_task(task_id, update_by=update_by)

    logger.info('[ResumeTask] 恢复指令已提交: task_id={}', task_id)
    return json.dumps({
        'success': True,
        'task_id': task_id,
        'summary': f'任务 {task_id} 恢复指令已提交，将异步继续爬取',
    }, ensure_ascii=False)
