"""filter_chain URL 匹配（与 crawl4ai URLPatternFilter use_glob=True 语义对齐）"""

from __future__ import annotations

import fnmatch
import re
from typing import Any
from urllib.parse import urlparse


def url_matches_pattern(url: str, pattern: str) -> bool:
    """单条 glob 模式匹配 URL"""
    if not url or not pattern:
        return False
    return fnmatch.fnmatch(url, pattern)


def url_matches_include_pattern(url: str, pattern: str) -> bool:
    """
    include 匹配（含目录根等价）。

    `https://host/docs/zh/*` 同时接纳 `https://host/docs/zh` 与 `https://host/docs/zh/`，
    避免入口 URL 因缺少尾斜杠 / 子路径被误判为越界。
    """
    if url_matches_pattern(url, pattern):
        return True
    if pattern.endswith('/*'):
        root = pattern[:-2].rstrip('/')
        return url.rstrip('/') == root
    return False


def url_matches_filter_chain(url: str, filter_chain: dict | None) -> bool:
    """
    判断 URL 是否被 filter_chain 保留。

    - include_patterns 非空：须匹配至少一条（含目录根等价）
    - exclude_patterns 非空：不得匹配任一条
    """
    if not filter_chain:
        return True

    include_patterns = filter_chain.get('include_patterns') or []
    exclude_patterns = filter_chain.get('exclude_patterns') or []

    if include_patterns and not any(url_matches_include_pattern(url, p) for p in include_patterns):
        return False
    if exclude_patterns and any(url_matches_pattern(url, p) for p in exclude_patterns):
        return False
    return True


def extract_deep_crawl_strategy(strategy_config: dict | None) -> dict | None:
    """从 strategy_config 提取 deep_crawl_strategy（兼容嵌套 / 顶层）"""
    if not strategy_config or not isinstance(strategy_config, dict):
        return None
    dcs = strategy_config.get('deep_crawl_strategy')
    if isinstance(dcs, dict):
        return dcs
    crawler_run = strategy_config.get('crawler_run_config')
    if isinstance(crawler_run, dict):
        nested = crawler_run.get('deep_crawl_strategy')
        if isinstance(nested, dict):
            return nested
    return None


def extract_filter_chain(strategy_config: dict | None) -> dict | None:
    """从 strategy_config 提取 deep_crawl_strategy.filter_chain"""
    deep = extract_deep_crawl_strategy(strategy_config)
    if not deep:
        return None
    fc = deep.get('filter_chain')
    if isinstance(fc, dict):
        # crawl4ai 序列化：{type, params: {include_patterns...}}
        params = fc.get('params')
        if isinstance(params, dict) and (
            'include_patterns' in params or 'exclude_patterns' in params
        ):
            return params
        return fc
    if isinstance(deep.get('params'), dict):
        nested = deep['params'].get('filter_chain')
        if isinstance(nested, dict):
            params = nested.get('params')
            if isinstance(params, dict) and (
                'include_patterns' in params or 'exclude_patterns' in params
            ):
                return params
            return nested
    return None


def _coerce_link_hrefs(links: dict | list | None) -> list[str]:
    """从 crawl4ai links 字段抽出 URL 列表（兼容 str / {href} / list）"""
    if not links:
        return []
    items: list[Any]
    if isinstance(links, dict):
        items = []
        for key in ('internal', 'external'):
            bucket = links.get(key)
            if isinstance(bucket, list):
                items.extend(bucket)
    elif isinstance(links, list):
        items = links
    else:
        return []

    hrefs: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            hrefs.append(item.strip())
        elif isinstance(item, dict):
            href = (item.get('href') or item.get('url') or '').strip()
            if href:
                hrefs.append(href)
    return hrefs


_MD_LINK_RE = re.compile(r'\[([^\]]*)\]\((https?://[^)\s]+)\)')


def extract_candidate_urls(
    *,
    links: dict | list | None = None,
    markdown: str | None = None,
) -> list[str]:
    """合并 links 字段与 Markdown 内链，去重保序"""
    seen: set[str] = set()
    result: list[str] = []
    for href in _coerce_link_hrefs(links):
        if href not in seen:
            seen.add(href)
            result.append(href)
    if markdown:
        for match in _MD_LINK_RE.finditer(markdown):
            href = match.group(2).strip()
            if href and href not in seen:
                seen.add(href)
                result.append(href)
    return result


def count_urls_in_filter(urls: list[str], filter_chain: dict | None) -> int:
    """统计命中 filter_chain 的 URL 数"""
    if not urls:
        return 0
    return sum(1 for u in urls if url_matches_filter_chain(u, filter_chain))


def suggest_seed_from_include_patterns(include_patterns: list[str]) -> list[str]:
    """
    从 include_patterns 推导建议入口 URL（去掉末尾 /*）。

    例：https://milvus.io/docs/zh/* → https://milvus.io/docs/zh/
    """
    suggestions: list[str] = []
    seen: set[str] = set()
    for pattern in include_patterns or []:
        if not pattern:
            continue
        seed = pattern[:-2] if pattern.endswith('/*') else pattern
        seed = seed.rstrip('/') + '/'
        parsed = urlparse(seed)
        if not parsed.scheme or not parsed.netloc:
            continue
        if seed not in seen:
            seen.add(seed)
            suggestions.append(seed)
    return suggestions


def looks_like_leaf_document_url(url: str) -> bool:
    """
    判断 URL 是否更像内容叶页（含扩展名），而非板块入口/枢纽。

    叶页试爬用于验证内容提取；出链可能本来就少，不应触发 NO_IN_SCOPE_EXPANSION
    并误导改回入口 URL。
    """
    path = (urlparse(url or '').path or '').rstrip('/')
    if not path:
        return False
    last = path.rsplit('/', 1)[-1]
    return '.' in last


def evaluate_seed_scope(
    seed_url: str,
    crawl_config: dict | None,
    *,
    pages_yielded: int = 0,
    pages_in_scope: int = 0,
    outbound_in_scope_count: int | None = None,
) -> dict[str, Any]:
    """
    评估起点与 include_patterns 的可达性。

    有 include 时：
    - 起点越界且试爬范围内页 < 2 → SEED_SCOPE_MISMATCH（禁止全量）
    - 起点在范围内、配置意图多页，但出链命中为 0 → NO_IN_SCOPE_EXPANSION
      （叶页 URL 跳过：失败修复场景常对具体文档试爬）
    """
    filter_chain = extract_filter_chain(crawl_config)
    include_patterns = list((filter_chain or {}).get('include_patterns') or [])
    deep = extract_deep_crawl_strategy(crawl_config) or {}

    seed_in_scope = True
    if include_patterns:
        seed_in_scope = url_matches_filter_chain(seed_url, filter_chain)

    issues: list[str] = []
    suggestions: list[str] = []
    suggested_seeds = suggest_seed_from_include_patterns(include_patterns)

    if include_patterns and not seed_in_scope:
        # 枢纽页起步：仅当试爬已扩到 ≥2 个范围内页才放行
        if pages_in_scope < 2:
            issues.append('SEED_SCOPE_MISMATCH')
            hint = '、'.join(suggested_seeds[:3]) if suggested_seeds else '目标板块入口 URL'
            suggestions.append(
                f'当前起点几乎扩不进目标板块，正式爬只会落到极少页面；'
                f'请让用户把目标网址改成板块入口（如 {hint}）后再爬，'
                f'勿仅私自改试爬 URL，也勿用 Cookie/反爬配置掩盖'
            )

    try:
        # null/-1 常被 LLM 写成「不限制」→ 视为多页意图；仅显式 0 视为单页
        raw_depth = deep.get('max_depth')
        max_depth = int(raw_depth) if raw_depth not in (None, '') else -1
    except (TypeError, ValueError):
        max_depth = -1
    try:
        max_pages_raw = deep.get('max_pages')
        max_pages = int(max_pages_raw) if max_pages_raw not in (None, '') else 0
    except (TypeError, ValueError):
        max_pages = 0
    intends_multi_page = (max_depth != 0) and (max_pages == 0 or max_pages > 3)

    if (
        include_patterns
        and seed_in_scope
        and intends_multi_page
        and outbound_in_scope_count is not None
        and outbound_in_scope_count <= 0
        and pages_in_scope <= 1
        and not looks_like_leaf_document_url(seed_url)
    ):
        issues.append('NO_IN_SCOPE_EXPANSION')
        suggestions.append(
            '起点在范围内但未发现命中 include 的出链，检查 filter_chain / css_selector / 等待策略，'
            '或改用文档树入口页'
        )

    return {
        'applicable': bool(include_patterns),
        'seed_in_scope': seed_in_scope,
        'pages_yielded': pages_yielded,
        'pages_in_scope': pages_in_scope,
        'outbound_in_scope_count': outbound_in_scope_count,
        'suggested_seed_urls': suggested_seeds,
        'expansion_ok': not issues,
        'issues': issues,
        'suggestions': suggestions,
    }


def compute_pages_to_remove(
    crawled_pages: list[dict],
    new_filter_chain: dict | None,
) -> list[dict]:
    """
    计算 rescope 后需删除的已爬 SUCCESS 页面。

    仍匹配新 filter 的 URL 不得列入删除列表。
    """
    if not crawled_pages or not new_filter_chain:
        return []

    result: list[dict] = []
    for page in crawled_pages:
        url = page.get('url') or ''
        if not url:
            continue
        if page.get('status') not in (None, 'SUCCESS'):
            continue
        if url_matches_filter_chain(url, new_filter_chain):
            continue
        result.append({
            'url': url,
            'title': page.get('title') or '',
            'reason': '新 filter_chain 不再匹配',
        })
    return result
