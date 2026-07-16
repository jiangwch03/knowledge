"""从渲染后 HTML 提取各版本对应的 URL 前缀（探针校准，非 LLM 猜测）"""

import re
from urllib.parse import urljoin, urlparse

from knowledge_content.service.vo.suggested_crawl_action_vo import VersionUrlPatternVo

_VERSION_LABEL_RE = re.compile(r'\bv(\d+(?:\.\d+){0,2}(?:\.x)?)\b', re.IGNORECASE)
_VERSION_PATH_RE = re.compile(
    r'/(?:v)?(\d+(?:\.\d+){0,2}(?:[._-]x)?)(?:/|$)',
    re.IGNORECASE,
)


def extract_version_url_patterns(page_url: str, html: str) -> list[VersionUrlPatternVo]:
    """
    扫描渲染后 HTML 中所有带版本号的路径链接，归纳出版本 → URL 前缀映射。

    例如某文档站渲染后可见：
      href="/docs/zh/v2.6.x/overview.md"  → prefix /docs/zh/v2.6.x
      href="/docs/v2.6.x/overview.md"      → prefix /docs/v2.6.x
    """
    if not html:
        return []

    parsed_base = urlparse(page_url)
    origin = f'{parsed_base.scheme}://{parsed_base.netloc}'
    base_path = parsed_base.path.rstrip('/')

    # 收集 (version_label, absolute_href)
    version_hrefs: dict[str, list[str]] = {}

    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.IGNORECASE):
        if href.startswith('#') or href.startswith('javascript:'):
            continue
        absolute = urljoin(page_url, href)
        path = urlparse(absolute).path
        vm = _VERSION_PATH_RE.search(path)
        if not vm:
            continue
        raw_ver = vm.group(1).replace('_', '.').lower()
        label = _normalize_version_label(raw_ver)
        version_hrefs.setdefault(label, []).append(absolute)

    patterns: list[VersionUrlPatternVo] = []
    lang_segment = _language_segment_from_path(base_path)

    # 按版本分组，每版本可有多条前缀（如 /docs/v2.6.x 与 /docs/zh/v2.6.x）
    by_version: dict[str, list[str]] = {}
    for label, hrefs in version_hrefs.items():
        by_version[label] = hrefs

    for label, hrefs in sorted(by_version.items()):
        best = _pick_best_href(hrefs, base_path, lang_segment)
        prefix_path = _extract_prefix_path(urlparse(best).path, label)
        if not prefix_path:
            continue
        url_prefix = f'{origin}{prefix_path}'
        include = f'{url_prefix}/*'
        patterns.append(VersionUrlPatternVo(
            version_label=label,
            url_prefix=url_prefix,
            include_pattern=include,
            sample_href=best,
            evidence=f'渲染后页面链接 href 含版本路径 {prefix_path}',
        ))

    return patterns


def _language_segment_from_path(base_path: str) -> str | None:
    """从 /docs/zh 提取语言段 zh"""
    parts = [p for p in base_path.strip('/').split('/') if p]
    if len(parts) >= 2 and parts[0] == 'docs' and not _VERSION_PATH_RE.search(f'/{parts[1]}/'):
        return parts[1]
    return None


def _normalize_version_label(raw: str) -> str:
    if not raw.endswith('.x') and raw.count('.') == 1:
        return f'v{raw}.x'
    if not raw.startswith('v'):
        return f'v{raw}'
    return f'v{raw.lstrip("v")}' if raw.startswith('v') else raw


def _extract_prefix_path(path: str, version_label: str) -> str:
    """从 /docs/zh/v2.6.x/overview.md 提取前缀 /docs/zh/v2.6.x"""
    ver_core = version_label.replace('.x', '').lstrip('v')
    pattern = re.compile(
        rf'(.*/v{re.escape(ver_core)}(?:\.x)?)(?:/|$)',
        re.IGNORECASE,
    )
    m = pattern.search(path)
    return m.group(1) if m else ''


def _pick_best_href(hrefs: list[str], base_path: str, lang_segment: str | None) -> str:
    """优先选与当前 URL 语言段 + 路径一致的版本链接"""
    if not hrefs:
        return ''

    def score(href: str) -> tuple[int, int]:
        path = urlparse(href).path
        path_parts = [p for p in path.strip('/').split('/') if p]
        common = 0
        for a, b in zip([p for p in base_path.strip('/').split('/') if p], path_parts):
            if a.lower() == b.lower():
                common += 1
            else:
                break
        lang_bonus = 0
        if lang_segment and f'/{lang_segment}/' in path.lower():
            lang_bonus = 10
        return (lang_bonus, common)

    return max(hrefs, key=score)
