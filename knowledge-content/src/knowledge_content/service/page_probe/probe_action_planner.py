"""从渲染 HTML 提取版本 URL 事实（不含策略/hooks，供 Agent 推理）"""

from knowledge_content.service.page_probe.version_url_extractor import extract_version_url_patterns
from knowledge_content.service.vo.suggested_crawl_action_vo import VersionUrlPatternVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo


def extract_version_url_facts(
    page_url: str,
    html: str,
    url_signals: UrlSignalsVo,
) -> list[VersionUrlPatternVo]:
    """
    ⑤ 弱化策略：仅提取渲染后链接中的版本 URL 前缀事实。

    不再输出 suggested_actions；是否采用 url_prefix 或 hooks 由 Planning Agent 决定。
    """
    if not html:
        return []

    patterns = extract_version_url_patterns(page_url, html)
    return _expand_language_version_prefixes(page_url, patterns)


def _expand_language_version_prefixes(
    page_url: str,
    patterns: list[VersionUrlPatternVo],
) -> list[VersionUrlPatternVo]:
    """当 URL 含语言段时，推断 /docs/{lang}/{version}/ 前缀（通用文档站模式）"""
    from urllib.parse import urlparse

    from knowledge_content.service.page_probe.url_signals_analyzer import analyze_url_signals

    signals = analyze_url_signals(page_url)
    if not signals.has_language_in_path or signals.has_version_in_path:
        return patterns

    parsed = urlparse(page_url)
    origin = f'{parsed.scheme}://{parsed.netloc}'
    lang = signals.language_patterns[0].strip('/').split('/')[0] if signals.language_patterns else ''
    if not lang:
        return patterns

    existing = {p.url_prefix for p in patterns}
    extra: list[VersionUrlPatternVo] = []
    for p in patterns:
        if f'/docs/{lang}/' in p.url_prefix:
            continue
        if '/docs/v' in p.url_prefix and f'/docs/{lang}/' not in p.url_prefix:
            suffix = p.url_prefix.split('/docs/', 1)[-1]
            zh_prefix = f'{origin}/docs/{lang}/{suffix}'
            if zh_prefix not in existing:
                extra.append(VersionUrlPatternVo(
                    version_label=p.version_label,
                    url_prefix=zh_prefix,
                    include_pattern=f'{zh_prefix}/*',
                    sample_href=p.sample_href,
                    evidence=f'由 {p.url_prefix} + 当前语言 {lang} 推断',
                ))
                existing.add(zh_prefix)
    return patterns + extra
