"""试爬质量门禁判定"""

import re
from typing import Any

from knowledge_content.agents.utils.filter_chain_util import (
    count_urls_in_filter,
    evaluate_seed_scope,
    extract_candidate_urls,
    extract_filter_chain,
    url_matches_filter_chain,
)
from knowledge_content.service.vo.trial_quality_gate_vo import TrialQualityGateVo

_LOGIN_RE = re.compile(r'\b(?:login|sign\s*in|登录|登入|password)\b', re.IGNORECASE)
_VERSION_MISMATCH_HINTS: list[tuple[str, re.Pattern[str]]] = [
    ('v3.0', re.compile(r'\bv3\.0', re.IGNORECASE)),
    ('v2.6', re.compile(r'\bv2\.6', re.IGNORECASE)),
    ('v2.5', re.compile(r'\bv2\.5', re.IGNORECASE)),
]


class TrialQualityGateService:
    """trial_crawl 结果质量门禁"""

    @classmethod
    def evaluate(
        cls,
        *,
        success: bool,
        title: str,
        markdown: str,
        status_code: int | None,
        expected_version: str | None = None,
        seed_url: str | None = None,
        crawl_config: dict | None = None,
        page_results: list[dict[str, Any]] | None = None,
    ) -> TrialQualityGateVo:
        """
        对试爬 Markdown 结果做质量门禁判定（含扩链可达性）

        :param success: 爬取是否成功（通常取首屏）
        :param title: 页面标题
        :param markdown: Markdown 正文（通常取首屏）
        :param status_code: HTTP 状态码
        :param expected_version: 探针或用户期望的版本（如 v2.6.x），可选
        :param seed_url: 试爬起点 URL，可选；提供时做 include 扩链门禁
        :param crawl_config: 原始策略配置（未限流前），可选
        :param page_results: 试爬 yield 的各页摘要 {url, success, links, markdown}，可选
        """
        content = (markdown or '').strip()
        word_count = len(content)
        heading_count = len(re.findall(r'^#{1,6}\s', content, re.MULTILINE))
        link_count = len(re.findall(r'\[([^\]]*)\]\(([^)]+)\)', content))
        preview = content[:300] if content else ''

        issues: list[str] = []
        suggestions: list[str] = []
        shell_risk = 'low'

        if not success:
            issues.append('CRAWL_FAILED')
            suggestions.append('检查 URL 是否可访问、超时与 wait_until 配置')
            shell_risk = 'high'
        elif status_code in (403, 429, 503):
            issues.append('HTTP_ERROR')
            suggestions.append('疑似反爬或访问受限，考虑代理或更长延迟')
            shell_risk = 'high'
        elif word_count < 50:
            issues.append('EMPTY_SHELL')
            suggestions.append(
                '正文过短：结合 diagnostics.html_length 判断——'
                'HTML有字则查 css_selector / content_filter；'
                'HTML也空则查 wait_until / redirected_url；勿只盲目加大 page_timeout'
            )
            shell_risk = 'high'
        elif word_count > 200 and heading_count == 0:
            issues.append('NO_HEADINGS')
            suggestions.append('正文无标题结构，可能 css_selector 抓错区域，调整正文选择器')
            shell_risk = 'medium'
        elif success and not (title or '').strip():
            issues.append('TITLE_MISSING')
            suggestions.append('页面可能未加载完成，增加 wait_for 等待主内容区')
            shell_risk = 'medium'

        if content and _LOGIN_RE.search(content[:500]):
            issues.append('LOGIN_REDIRECT')
            suggestions.append('页面可能需要登录，向用户追问 Cookie 或账号')
            shell_risk = 'high'

        if expected_version and content:
            mismatch = cls._detect_version_mismatch(expected_version, content)
            if mismatch:
                issues.append('VERSION_MISMATCH')
                suggestions.append(
                    f'正文疑似为 {mismatch} 而非期望 {expected_version}，请结合探针 version_url_patterns 与 interactive_elements 调整 URL 或 hooks',
                )
                shell_risk = 'high'

        if shell_risk == 'low' and word_count < 300:
            shell_risk = 'medium'

        expansion = cls._evaluate_expansion(
            seed_url=seed_url or '',
            crawl_config=crawl_config,
            page_results=page_results or [],
        )
        issues.extend(expansion['issues'])
        suggestions.extend(expansion['suggestions'])
        if expansion['issues']:
            shell_risk = 'high' if 'SEED_SCOPE_MISMATCH' in expansion['issues'] else (
                'medium' if shell_risk == 'low' else shell_risk
            )

        passed = not issues

        return TrialQualityGateVo(
            passed=passed,
            shell_risk=shell_risk,
            issues=issues,
            content_preview=preview,
            word_count=word_count,
            heading_count=heading_count,
            link_count=link_count,
            suggestions=suggestions,
            expansion_ok=expansion['expansion_ok'],
            seed_in_scope=expansion['seed_in_scope'],
            pages_yielded=expansion['pages_yielded'],
            pages_in_scope=expansion['pages_in_scope'],
            outbound_in_scope_count=expansion['outbound_in_scope_count'],
            suggested_seed_urls=expansion['suggested_seed_urls'],
        )

    @classmethod
    def _evaluate_expansion(
        cls,
        *,
        seed_url: str,
        crawl_config: dict | None,
        page_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """汇总试爬扩链指标并判定 seed↔include 门禁"""
        if not seed_url or not crawl_config:
            return {
                'expansion_ok': True,
                'seed_in_scope': True,
                'pages_yielded': len(page_results),
                'pages_in_scope': 0,
                'outbound_in_scope_count': None,
                'suggested_seed_urls': [],
                'issues': [],
                'suggestions': [],
            }

        filter_chain = extract_filter_chain(crawl_config)
        pages_yielded = len(page_results)
        pages_in_scope = 0
        outbound_in_scope_count: int | None = None

        for idx, page in enumerate(page_results):
            page_url = (page.get('url') or '').strip()
            if page_url and url_matches_filter_chain(page_url, filter_chain):
                pages_in_scope += 1
            if idx == 0:
                candidates = extract_candidate_urls(
                    links=page.get('links'),
                    markdown=page.get('markdown'),
                )
                outbound_in_scope_count = count_urls_in_filter(candidates, filter_chain)

        return evaluate_seed_scope(
            seed_url,
            crawl_config,
            pages_yielded=pages_yielded,
            pages_in_scope=pages_in_scope,
            outbound_in_scope_count=outbound_in_scope_count,
        )

    @classmethod
    def _detect_version_mismatch(cls, expected_version: str, content: str) -> str | None:
        """若正文明显为错误版本，返回检测到的版本；已切到期望版本则返回 None"""
        expected_norm = expected_version.lower().replace('.x', '').lstrip('v')
        head = content[:1200]

        # 首页链接路径已含期望版本 → 已校准（如 /docs/zh/v2.6.x）
        home_match = re.search(r'\[首页\]\(([^)]+)\)', head)
        if home_match and re.search(
            rf'/v{re.escape(expected_norm)}(?:\.x)?/',
            home_match.group(1),
            re.IGNORECASE,
        ):
            return None

        # 导航区独立行的当前激活版本（非下拉里的其他版本链接）
        active = cls._extract_active_version_line(head)
        if active:
            active_norm = active.lower().replace('.x', '').lstrip('v')
            if active_norm == expected_norm or active_norm.startswith(expected_norm[:3]):
                return None
            return active

        body = content[1200:3200] if len(content) > 1200 else content[800:]
        expected_key = expected_norm[:3]
        for label, pattern in _VERSION_MISMATCH_HINTS:
            if label.replace('.x', '').lstrip('v')[:3] == expected_key:
                continue
            if pattern.search(body):
                return label
        return None

    @classmethod
    def _extract_active_version_line(cls, head: str) -> str | None:
        """从 Markdown 导航区提取当前激活版本（独立行 vX.X.x）"""
        for line in head[:800].splitlines():
            stripped = line.strip()
            m = re.match(r'^(v\d+\.\d+(?:\.x)?)$', stripped, re.IGNORECASE)
            if m:
                return m.group(1)
        return None
