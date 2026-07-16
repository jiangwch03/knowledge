"""文档版本号识别工具（站点无关；过滤 api-v1 / JSON 噪声）"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 文档站版本：v2.6 / v2.6.x / v3.0.1（自由文本要求带 v，降噪）
_DOC_VERSION_RE = re.compile(
    r'\bv(\d+)\.(\d+)(?:\.(\d+))?(?:\.x)?\b',
    re.IGNORECASE,
)

# 控件上下文可放宽：2.6.0 / 1.28 / v3.0.x（Docusaurus / K8s 等常不带 v）
_STRUCT_VERSION_RE = re.compile(
    r'\b(?:v)?(\d+)\.(\d+)(?:\.(?:\d+|x))?\b',
    re.IGNORECASE,
)

# 裸 v1/v2（无 minor）多为 API 路径噪声
_BARE_VERSION_RE = re.compile(r'\bv(\d+)\b', re.IGNORECASE)

_SCRIPT_STYLE_RE = re.compile(
    r'<script[^>]*>.*?</script>|<style[^>]*>.*?</style>',
    re.DOTALL | re.IGNORECASE,
)

_SELECT_RE = re.compile(r'<select[^>]*>(.*?)</select>', re.DOTALL | re.IGNORECASE)
_OPTION_RE = re.compile(r'<option[^>]*>([^<]+)</option>', re.IGNORECASE)

# ARIA 下拉菜单容器（无站点特有 class）
_LISTBOX_RE = re.compile(
    r'<(?P<tag>ul|ol|div|menu)(?P<attrs>[^>]*\brole=["\'](?:listbox|menu)["\'][^>]*)>'
    r'(?P<body>.*?)</(?P=tag)>',
    re.DOTALL | re.IGNORECASE,
)

# 任意带 aria-haspopup 的触发器（listbox/menu/true）
_POPUP_TRIGGER_RE = re.compile(
    r'<(?P<tag>button|div|a|span)(?P<attrs>[^>]*\baria-haspopup=["\']'
    r'(?:listbox|menu|true)["\'][^>]*)>(?P<body>.*?)</(?P=tag)>',
    re.DOTALL | re.IGNORECASE,
)

# 紧凑版本链接簇：同一列表内多个「文档版本路径」链接
_VERSION_HREF_RE = re.compile(
    r'href=["\']([^"\']*?/(?:v)?\d+\.\d+(?:\.(?:\d+|x))?[^"\']*)["\']',
    re.IGNORECASE,
)
_LIST_CLUSTER_RE = re.compile(
    r'<(?P<tag>ul|ol|div)(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>',
    re.DOTALL | re.IGNORECASE,
)


@dataclass
class VersionSwitcherSignal:
    """版本选择器探测结果（结构信号优先于自由文本）"""

    options: list[str] = field(default_factory=list)
    current_value: str = ''
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    location: str = 'unknown'
    from_select: bool = False
    from_listbox: bool = False
    from_trigger: bool = False
    from_link_cluster: bool = False


def strip_script_style(html: str) -> str:
    """去掉 script/style，避免内嵌 JSON 里的 api-v1 干扰版本检测"""
    text = _SCRIPT_STYLE_RE.sub(' ', html)
    return re.sub(r'\s+', ' ', text).strip()


def extract_doc_version_labels(text: str) -> list[str]:
    """
    从可见文本提取文档版本标签（去重）。

    排除 api-v1 类噪声：要求至少 major.minor 且带 v 前缀。
    major/minor > 99 视为 SVG 坐标等噪声。
    """
    labels: list[str] = []
    for m in _DOC_VERSION_RE.finditer(text or ''):
        if int(m.group(1)) > 99 or int(m.group(2)) > 99:
            continue
        label = m.group(0)
        if label.lower() not in {x.lower() for x in labels}:
            labels.append(label)
    return labels


def extract_structural_version_labels(text: str) -> list[str]:
    """从控件/菜单上下文提取版本标签（允许不带 v 的 2.6.0 / 1.28）。"""
    labels: list[str] = []
    for m in _STRUCT_VERSION_RE.finditer(text or ''):
        label = m.group(0)
        # 排除明显不是版本的小数噪声（如 SVG 坐标 10.6967）
        major = int(m.group(1))
        minor = int(m.group(2))
        if major > 99 or minor > 99:
            continue
        if label.lower() not in {x.lower() for x in labels}:
            labels.append(label)
    return labels


def is_likely_doc_version_switcher(options: list[str], *, from_select: bool = False) -> bool:
    """判断是否像文档版本选择器（而非 API 版本字符串）"""
    doc_like = [o for o in options if _DOC_VERSION_RE.search(o) or _STRUCT_VERSION_RE.fullmatch(o.strip())]
    if from_select and len(doc_like) >= 2:
        return True
    if len(doc_like) >= 2:
        return True
    bare_only = all(_BARE_VERSION_RE.fullmatch(o.strip()) for o in options if o.strip())
    return len(doc_like) >= 2 and not bare_only


def _append_unique(options: list[str], labels: list[str]) -> int:
    """追加去重版本标签，返回新增数量"""
    added = 0
    existing = {x.lower() for x in options}
    for label in labels:
        key = label.lower()
        if key not in existing:
            options.append(label)
            existing.add(key)
            added += 1
    return added


def _plain_text(fragment: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', fragment or '')).strip()


def _guess_location(html: str) -> str:
    """站点无关位置启发式：侧栏 / 顶栏 / 未知"""
    lower = (html or '').lower()
    if re.search(r'<aside\b|sidebar|side-nav|side_nav|left-?nav|docs-nav', lower):
        return 'sidebar'
    if re.search(r'<header\b|<nav\b|navbar|top-?nav', lower):
        return 'header'
    return 'unknown'


def detect_version_switcher_signal(html: str, visible_text: str = '') -> VersionSwitcherSignal | None:
    """
    站点无关版本选择器探测。

    通道（按结构优先）：
    ① native <select> 含 ≥2 版本 option
    ② role=listbox|menu 内含 ≥2 版本文本/链接
    ③ 同一列表容器内 ≥2 个版本路径链接（紧凑链接簇）
    ④ aria-haspopup 触发器文案本身是文档版本（关闭态菜单未挂载）
    ⑤ 去 script 后全文 ≥2 个带 v 的文档版本（弱证据）
    """
    html = html or ''
    visible_text = visible_text or ''
    signal = VersionSwitcherSignal(location=_guess_location(html))
    options: list[str] = []

    # ⑤ 全文（不做长度截断；脚本已剥离）
    clean_text = strip_script_style(html) if html else visible_text
    free_labels = extract_doc_version_labels(f'{visible_text}\n{clean_text}')
    _append_unique(options, free_labels)

    # ① native select
    for block in _SELECT_RE.findall(html):
        raw_opts = [_plain_text(t) for t in _OPTION_RE.findall(block)]
        labels = []
        for t in raw_opts:
            labels.extend(extract_structural_version_labels(t))
        # 去重保序
        labels = list(dict.fromkeys(labels))
        if len(labels) >= 2:
            signal.from_select = True
            signal.evidence.append('select 含版本号选项')
            _append_unique(options, labels)

    # ② ARIA listbox / menu
    for m in _LISTBOX_RE.finditer(html):
        body = m.group('body') or ''
        labels = extract_structural_version_labels(_plain_text(body))
        for href in _VERSION_HREF_RE.findall(body):
            labels.extend(extract_structural_version_labels(href))
        labels = list(dict.fromkeys(labels))
        if len(labels) >= 2:
            signal.from_listbox = True
            signal.evidence.append('ARIA listbox/menu 含多版本选项')
            _append_unique(options, labels)

    # ③ 紧凑版本链接簇：只在已含版本路径的小容器上判定（避免全页扫 div）
    for m in _LIST_CLUSTER_RE.finditer(html):
        body = m.group('body') or ''
        if len(body) > 4000 or not _VERSION_HREF_RE.search(body):
            continue
        href_labels: list[str] = []
        for href in _VERSION_HREF_RE.findall(body):
            href_labels.extend(extract_structural_version_labels(href))
        href_labels = list(dict.fromkeys(href_labels))
        if len(href_labels) >= 2:
            signal.from_link_cluster = True
            signal.evidence.append('同一容器内多个版本路径链接')
            _append_unique(options, href_labels)
            _append_unique(options, extract_structural_version_labels(_plain_text(body)))

    # ④ 关闭态触发器
    for m in _POPUP_TRIGGER_RE.finditer(html):
        trigger_labels = extract_structural_version_labels(_plain_text(m.group('body') or ''))
        if trigger_labels:
            signal.from_trigger = True
            signal.evidence.append('aria-haspopup 触发器文案为版本号')
            _append_unique(options, trigger_labels)
            break

    structural = (
        signal.from_select
        or signal.from_listbox
        or signal.from_link_cluster
        or signal.from_trigger
    )

    doc_options = [
        o for o in options
        if _DOC_VERSION_RE.search(o) or _STRUCT_VERSION_RE.fullmatch(o.strip())
    ]
    # 结构控件：允许不带 v；自由文本路径仍以 is_likely 约束
    if structural and len(doc_options) >= 2:
        pass
    elif signal.from_trigger and len(doc_options) >= 1:
        signal.evidence.append('关闭态仅见当前版本，展开后才有完整选项')
    elif is_likely_doc_version_switcher(doc_options, from_select=False):
        signal.evidence.append(f'文档版本文本: {", ".join(doc_options[:4])}')
    else:
        return None

    signal.options = doc_options[:10] or options[:10]
    signal.current_value = signal.options[0] if signal.options else ''

    if signal.from_select or signal.from_listbox:
        signal.confidence = 0.85
    elif signal.from_link_cluster:
        signal.confidence = 0.8
    elif signal.from_trigger:
        signal.confidence = 0.7 if len(signal.options) >= 2 else 0.6
    else:
        signal.confidence = 0.75

    if not signal.evidence:
        signal.evidence = [f'文档版本文本: {", ".join(signal.options[:4])}']
    return signal
