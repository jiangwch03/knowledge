"""
crawl_execute 正式爬取执行工具

使用 LLM 确认的爬取策略配置，通过 MessageStream 提交后台爬取任务。
返回任务 ID 和初始状态；用户后续询问进度时再通过 query_crawl_task 查询。

与 trial_crawl 的区别：
- trial_crawl: 限流试探，验证配置并写入 url+config 指纹凭证
- crawl_execute: 校验凭证后提交后台全站爬取任务（本工具不重跑试爬）

注意：
- target_url：由 LLM 显式传入（会话当前要爬的起点），审批弹窗展示该值供用户把关
- runtime.context：身份上下文（session_id/user_id/dept_id/user_name/model_id），由入口 astream(context=...) 注入
"""

import hashlib
import json

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.crawl_submit_gate import (
    CrawlSubmitPrepared,
    prepare_crawl_submit,
)
from knowledge_content.agents.utils.strategy_config_util import CrawlConfigArg
from knowledge_content.service.vo.crawl_task_create_vo import CrawlTaskCreateVo
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService


@tool
async def crawl_execute(
    target_url: str,
    crawl_config: CrawlConfigArg = None,
    runtime: ToolRuntime = None,
) -> str:
    """
    提交后台爬取任务，返回任务摘要 JSON。

    当 LLM 确认爬取策略配置后，调用此工具提交正式爬取任务。
    须显式传入本次要爬的目标网址（用户确认的入口 URL）。
    提交前会校验：本会话已对相同 target_url + crawl_config 试爬成功；否则拒绝并请先试爬。
    任务将异步执行；仅在用户询问进度时调用 query_crawl_task，勿自动轮询。

    返回包含以下信息的 JSON 字符串：
    - task_id: 任务 ID（可用于后续进度查询）
    - status: 任务状态（PENDING / RUNNING / COMPLETED / FAILED）
    - doc_version: 文档版本号
    - estimated_pages: 预估爬取页面数
    - url: 爬取目标 URL
    - summary: 简要结果描述

    Args:
        target_url: 本次爬取起点 URL（须与用户确认的入口一致，会展示在审批弹窗）
        crawl_config: 完整爬取策略配置的 JSON 字符串（须为对象序列化结果，禁止再包一层引号），为空时使用默认配置
    """
    prepared = await prepare_crawl_submit(
        runtime=runtime,
        crawl_config_arg=crawl_config,
        target_url=target_url,
        require_nonempty_config=False,
        log_tag='CrawlExecute',
        action_hint='再提交',
    )
    if not isinstance(prepared, CrawlSubmitPrepared):
        return prepared

    target_url = prepared.target_url
    parsed_config = prepared.crawl_config
    identity = prepared.identity

    try:
        logger.info('[CrawlExecute] 提交后台爬取任务: url={}', target_url)

        url_hash = hashlib.md5(target_url.encode()).hexdigest()
        lock_key = LockKey.custom_key(f'crawl:task:create:{url_hash}')
        async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
            if not acquired:
                logger.warning('[CrawlExecute] 该 URL 正在创建任务，跳过重复提交: url={}', target_url)
                return json.dumps({
                    'success': False,
                    'task_id': None,
                    'status': 'failed',
                    'url': target_url,
                    'summary': '该 URL 正在创建任务，请勿重复提交',
                    'message': '该 URL 正在创建任务，请勿重复提交',
                }, ensure_ascii=False)

            vo = CrawlTaskCreateVo(
                target_url=target_url,
                crawl_config=parsed_config,
                session_id=identity.session_id,
                user_id=identity.user_id,
                dept_id=identity.dept_id,
                create_by=identity.user_name,
            )
            task = await WebCrawlerTaskService.create_task(vo)

        logger.info(
            '[CrawlExecute] 任务已提交: task_id={}, doc_version={}, url={}, estimated_pages={}',
            task.task_id, task.doc_version, target_url, task.total_count,
        )

        return json.dumps({
            'success': True,
            'task_id': task.task_id,
            'status': task.status,
            'doc_version': task.doc_version,
            'estimated_pages': task.total_count,
            'url': target_url,
            'summary': (
                f'爬取任务已提交（ID={task.task_id}，版本={task.doc_version}），'
                f'预估爬取 {task.total_count or "未知"} 个页面'
            ),
        }, ensure_ascii=False)

    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[CrawlExecute] 提交任务异常: {}', err)
        return json.dumps({
            'success': False,
            'task_id': None,
            'status': 'failed',
            'url': target_url,
            'summary': f'提交爬取任务失败: {err}',
            'message': f'提交爬取任务失败: {err}',
        }, ensure_ascii=False)
