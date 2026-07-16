"""
网页爬取 Agent 生成工具 - 试探性爬取

使用 LLM 生成的爬取配置，对目标 URL 进行一次试探性爬取，
返回结构化摘要供 LLM 评估配置效果，支持迭代优化。

试爬成功后按 session 写入 url+config 指纹凭证，供 crawl_execute 提交前校验。

与正式爬取的区别：
- 只爬取首页或代表性页面（限流 2～3 页），不触发全站深度爬取
- 返回精简摘要（成功/失败、页面标题、内容长度、反爬状态、扩链指标）
- 不触发后处理流水线（MinIO 上传、文档落库等）
"""

import json
from typing_extensions import Annotated

from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from knowledge_common.agent.schema.context import get_agent_identity_from_tool_runtime
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.strategy_config_util import (
    CrawlConfigArgRequired,
    parse_tool_crawl_config,
)
from knowledge_content.agents.utils.trial_verified_gate import mark_trial_verified
from knowledge_content.service.trial_crawl_service import TrialCrawlService


@tool
async def trial_crawl(
    url: str,
    crawl_config: CrawlConfigArgRequired,
    state: Annotated[dict, InjectedState] = None,
    runtime: ToolRuntime = None,
) -> str:
    """
    使用指定的爬取配置试探性抓取页面，返回结果摘要 JSON。

    当您需要验证生成的爬取配置是否生效时调用此工具。
    例如：试爬能否正常加载页面、是否被反爬拦截、内容长度是否符合预期。
    有 include_patterns 时还会校验起点是否在范围内、能否扩出范围内链接。
    成功后会写入试爬凭证；正式提交须使用相同 url + crawl_config，否则提交会被拒绝。

    输入目标URL和爬取配置，返回包含以下信息的JSON字符串：
    - success: 是否成功
    - title: 页面标题
    - status_code: HTTP 状态码
    - content_length: 页面 Markdown 内容长度
    - html_length: 原始 HTML 长度（诊断空正文用）
    - redirected_url: 最终跳转 URL（若有）
    - diagnostics: 空正文/失败时的调参依据（含 extraction_hint、content_preview）
    - error: 失败时的错误信息（如有）
    - anti_crawl_detected: 是否检测到反爬机制
    - pages_yielded / pages_in_scope / outbound_in_scope_count / expansion_ok: 扩链指标
    - quality_gate: 质量门禁（passed、issues、content_preview、suggestions）
    - trial_verified: 是否已写入正式提交所需的试爬凭证

    Args:
        url: 目标页面 URL
        crawl_config: 爬取策略配置的 JSON 字符串（crawl4ai 参数对象序列化结果），必填
        state: 由 ToolNode 自动注入的图状态（不暴露给 LLM；可选期望版本等）
        runtime: 由框架注入，用于读取 session 身份（不暴露给 LLM）
    """
    if not url:
        logger.error('[TrialCrawl] url 为空')
        return json.dumps({'success': False, 'error': 'URL 不能为空', 'url': ''}, ensure_ascii=False)

    try:
        parsed_config = parse_tool_crawl_config(crawl_config)
    except ValueError as e:
        logger.exception('[TrialCrawl] crawl_config 解析失败: {}', e)
        return json.dumps({'success': False, 'error': f'爬取配置解析失败: {e}', 'url': url}, ensure_ascii=False)

    if not parsed_config:
        logger.error('[TrialCrawl] crawl_config 为空')
        return json.dumps({'success': False, 'error': '爬取配置不能为空', 'url': url}, ensure_ascii=False)

    try:
        expected_version = state.get('expected_doc_version') if state else None
        summary = await TrialCrawlService.run_trial(
            url,
            parsed_config,
            expected_version=expected_version,
        )

        # 成功：写入 session 级试爬凭证（正式提交只验凭证，不重跑试爬）
        summary['trial_verified'] = False
        if summary.get('success'):
            try:
                identity = get_agent_identity_from_tool_runtime(runtime)
                await mark_trial_verified(identity.session_id, url, parsed_config)
                summary['trial_verified'] = True
            except Exception as e:
                err = format_exception_message(e)
                logger.exception('[TrialCrawl] 写入试爬凭证失败: {}', err)
                summary['success'] = False
                summary['error'] = f'试爬通过但凭证写入失败，无法用于正式提交: {err}'
                summary['trial_verified'] = False

        return json.dumps(summary, ensure_ascii=False)

    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[TrialCrawl] 异常: {}', err)
        return json.dumps({'success': False, 'error': err, 'url': url}, ensure_ascii=False)
