"""URL 路径信号分析（纯字符串，不依赖页面渲染）"""

import re
from urllib.parse import urlparse

from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo

_VERSION_IN_PATH_RE = re.compile(
    r'/(?:v?\d+(?:\.\d+){0,2}(?:[._-]x)?|release[-_]?\d+(?:\.\d+)*)',
    re.IGNORECASE,
)
_LANGUAGE_IN_PATH_RE = re.compile(
    r'/(?:zh(?:-hant|-cn)?|en(?:-us|-gb)?|ja|ko|fr|de|es|pt|ru)(?:/|$)',
    re.IGNORECASE,
)


def analyze_url_signals(url: str) -> UrlSignalsVo:
    """从 URL 路径提取版本/语言信号"""
    parsed = urlparse(url)
    path = parsed.path or '/'
    segments = [s for s in path.strip('/').split('/') if s]

    version_matches = _VERSION_IN_PATH_RE.findall(path)
    language_matches = _LANGUAGE_IN_PATH_RE.findall(path)

    return UrlSignalsVo(
        has_version_in_path=bool(version_matches),
        has_language_in_path=bool(language_matches),
        version_patterns=list(dict.fromkeys(version_matches))[:5],
        language_patterns=list(dict.fromkeys(language_matches))[:5],
        path_depth=len(segments),
    )
