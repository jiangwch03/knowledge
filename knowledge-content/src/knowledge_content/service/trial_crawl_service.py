"""
限流试爬服务

供 trial_crawl 工具复用（正式提交只验指纹凭证，不在此重跑）：
- 将 deep_crawl 压到 2～3 页 / depth≤1
- 跑 crawl_stream 并做质量门禁 / 扩链判定
- 不触发后处理与任务落库
"""

from __future__ import annotations

import copy
from typing import Any

from knowledge_common.utils.log_util import logger
from knowledge_content.infra.crawl4ai import Crawl4aiClient
from knowledge_content.service.crawl_failure_diagnostics import (
    diagnostics_from_crawl_result,
    format_empty_content_message,
)
from knowledge_content.service.trial_quality_gate_service import TrialQualityGateService

# 试爬深度限流：上限 3 页 / depth 1
# crawl4ai BFS._arun_stream 在 max_pages=1 时会先 break 再 yield，导致空结果，故下限至少为 2
TRIAL_MAX_PAGES = 3
TRIAL_MIN_PAGES = 2
TRIAL_MAX_DEPTH = 1


def clamp_trial_deep_crawl_limits(strategy: dict) -> None:
    """
    将 deep_crawl_strategy 的 max_pages / max_depth 压到试爬安全区间。

    - max_pages 为 null / ≤0（正式配置表示不限制）→ 使用试爬上限 3
    - 显式值夹紧到 [TRIAL_MIN_PAGES, TRIAL_MAX_PAGES]，避免 stream=True 时空 yield
    - max_depth 为 null / ≤0（含 -1，LLM 常表示不限制）→ 试爬用 1，以便验证扩链
    - 显式正深度夹紧到 [1, TRIAL_MAX_DEPTH]
    """
    raw_pages = strategy.get('max_pages')
    if raw_pages is None or raw_pages == '' or (
        isinstance(raw_pages, (int, float)) and raw_pages <= 0
    ):
        strategy['max_pages'] = TRIAL_MAX_PAGES
    else:
        strategy['max_pages'] = min(max(int(raw_pages), TRIAL_MIN_PAGES), TRIAL_MAX_PAGES)

    raw_depth = strategy.get('max_depth')
    if raw_depth is None or raw_depth == '' or (
        isinstance(raw_depth, (int, float)) and raw_depth <= 0
    ):
        strategy['max_depth'] = TRIAL_MAX_DEPTH
    else:
        strategy['max_depth'] = min(max(int(raw_depth), 1), TRIAL_MAX_DEPTH)


def apply_trial_deep_crawl_limits(crawl_config: dict) -> dict:
    """
    深拷贝配置并将 deep_crawl 限流到试爬区间（不改动入参原对象）。
    """
    safe_config = copy.deepcopy(crawl_config)
    dcs_parent = safe_config
    if isinstance(safe_config.get('crawler_run_config'), dict):
        dcs_parent = safe_config['crawler_run_config']
    strategy = dcs_parent.get('deep_crawl_strategy')
    if isinstance(strategy, dict):
        clamp_trial_deep_crawl_limits(strategy)
    return safe_config


class TrialCrawlService:
    """限流试爬：validate → clamp → stream → quality_gate 摘要"""

    @classmethod
    async def run_trial(
        cls,
        url: str,
        crawl_config: dict,
        *,
        expected_version: str | None = None,
    ) -> dict[str, Any]:
        """
        对目标 URL 做限流试爬并返回与 trial_crawl 工具一致的摘要 dict。

        :param url: 起点 URL
        :param crawl_config: 正式策略配置（本方法内部限流，不修改调用方对象）
        :param expected_version: 可选期望文档版本
        :return: 含 success / quality_gate / expansion_ok 等字段的摘要
        """
        if not url:
            return {'success': False, 'error': 'URL 不能为空', 'url': ''}
        if not crawl_config:
            return {'success': False, 'error': '爬取配置不能为空', 'url': url}

        logger.info('[TrialCrawlService] 试探性爬取: url={}', url)

        # 1. 参数结构校验（与正式爬同一 ConfigBuilder 链路）
        Crawl4aiClient.validate_config(crawl_config)

        # 2. 安全限流：实际执行 max_pages≤3 / max_depth≤1
        safe_config = apply_trial_deep_crawl_limits(crawl_config)
        dcs_parent = safe_config.get('crawler_run_config') or safe_config
        strategy = dcs_parent.get('deep_crawl_strategy') if isinstance(dcs_parent, dict) else None
        if isinstance(strategy, dict):
            logger.info(
                '[TrialCrawlService] 限制 deep_crawl_strategy: max_pages={}, max_depth={}, url={}',
                strategy.get('max_pages'), strategy.get('max_depth'), url,
            )

        # 3. 收集本轮全部 yield，用于扩链门禁
        page_results: list[dict] = []
        first = None
        async for result in Crawl4aiClient.crawl_stream(url, safe_config):
            if first is None:
                first = result
            page_results.append({
                'url': result.url,
                'success': result.success,
                'links': result.links,
                'markdown': result.markdown or '',
            })

        if first is None:
            return {'success': False, 'error': '爬取无返回结果', 'url': url}

        markdown = first.markdown or ''
        diagnostics = diagnostics_from_crawl_result(first, requested_url=url)
        quality_gate = TrialQualityGateService.evaluate(
            success=first.success,
            title=first.title or '',
            markdown=markdown,
            status_code=first.status_code,
            expected_version=expected_version,
            seed_url=url,
            crawl_config=crawl_config,
            page_results=page_results,
        )
        # 硬阻塞：内容空洞 / 真正扩链失败；TITLE_MISSING 等仅 warning
        _hard_fail_issues = {
            'EMPTY_SHELL',
            'CRAWL_FAILED',
            'HTTP_ERROR',
            'LOGIN_REDIRECT',
            'SEED_SCOPE_MISMATCH',
            'NO_IN_SCOPE_EXPANSION',
            'VERSION_MISMATCH',
        }
        hard_issues = _hard_fail_issues.intersection(quality_gate.issues)
        summary: dict[str, Any] = {
            'success': bool(first.success) and not hard_issues,
            'url': first.url,
            'title': first.title or '',
            'status_code': first.status_code,
            'content_length': len(markdown),
            'html_length': first.html_length,
            'redirected_url': first.redirected_url,
            'anti_crawl_detected': False,
            'error': first.error_message if not first.success else None,
            'pages_yielded': quality_gate.pages_yielded,
            'pages_in_scope': quality_gate.pages_in_scope,
            'outbound_in_scope_count': quality_gate.outbound_in_scope_count,
            'expansion_ok': quality_gate.expansion_ok,
            'seed_in_scope': quality_gate.seed_in_scope,
            'suggested_seed_urls': quality_gate.suggested_seed_urls,
            'quality_gate': quality_gate.model_dump(),
            'diagnostics': diagnostics,
        }

        # 反爬仅认明确信号；EMPTY_SHELL / TITLE_MISSING / 扩链问题只进 warning
        _anti_issues = {'HTTP_ERROR', 'LOGIN_REDIRECT'}
        if first.status_code in (403, 429, 503) or _anti_issues.intersection(quality_gate.issues):
            summary['anti_crawl_detected'] = True
            if first.status_code in (403, 429, 503):
                summary['warning'] = f'HTTP {first.status_code}，疑似触发反爬'
        if first.success:
            content = markdown.strip()
            if not quality_gate.passed:
                if not summary.get('warning'):
                    summary['warning'] = '、'.join(quality_gate.issues) or '质量门禁未通过'
                # 仅真正起点越界才引导换入口；叶页 EMPTY_SHELL / NO_IN_SCOPE 不得改口换 seed
                if 'SEED_SCOPE_MISMATCH' in quality_gate.issues:
                    seeds = quality_gate.suggested_seed_urls[:3]
                    hint = '、'.join(seeds) if seeds else '板块入口 URL'
                    ask_user = (
                        f'当前起点 {url} 几乎扩不进目标板块，正式爬只会落到极少页面。'
                        f'请改用建议入口后再爬：{hint}（须用户确认更换目标网址，禁止仅私自改试爬 URL）'
                    )
                    summary['ask_user'] = ask_user
                    summary['needs_user_confirm_new_url'] = True
                    summary['error'] = ask_user
                    summary['success'] = False
                elif 'EMPTY_SHELL' in quality_gate.issues:
                    summary['error'] = format_empty_content_message(
                        content_length=len(content),
                        html_length=first.html_length,
                        status_code=first.status_code,
                        redirected_url=first.redirected_url,
                        title=first.title,
                        markdown=content,
                        requested_url=url,
                        final_url=first.url,
                    )
                    summary['success'] = False
                elif 'NO_IN_SCOPE_EXPANSION' in quality_gate.issues:
                    summary['error'] = (
                        '起点在范围内但未扩出命中 include 的出链；'
                        '请检查 filter_chain / 等待策略，或确认是否应换文档树入口'
                    )
                    summary['success'] = False
            elif len(content) < 50 and not summary['anti_crawl_detected']:
                summary['warning'] = '内容过短（<50字符），更可能是等待/选择器问题，未必是反爬'
                summary['success'] = False
                summary['error'] = format_empty_content_message(
                    content_length=len(content),
                    html_length=first.html_length,
                    status_code=first.status_code,
                    redirected_url=first.redirected_url,
                    title=first.title,
                    markdown=content,
                    requested_url=url,
                    final_url=first.url,
                )

        # 硬失败：首屏爬失败（超时/选择器等）必须 success=false，供提交门禁拦截
        if not first.success:
            summary['success'] = False
            if not summary.get('error'):
                summary['error'] = first.error_message or '试爬首屏失败'

        logger.info(
            '[TrialCrawlService] 结果: success={}, title={}, content_len={}, html_len={}, '
            'pages_yielded={}, pages_in_scope={}, outbound_in_scope={}, expansion_ok={}, '
            'anti_crawl={}, redirected={}',
            summary['success'], summary['title'], summary['content_length'],
            summary.get('html_length'), summary['pages_yielded'], summary['pages_in_scope'],
            summary['outbound_in_scope_count'], summary['expansion_ok'],
            summary['anti_crawl_detected'], summary.get('redirected_url'),
        )
        return summary
