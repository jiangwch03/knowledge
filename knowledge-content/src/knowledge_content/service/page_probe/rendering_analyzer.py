"""渲染模式与空壳风险判定"""

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.rendering_probe_vo import RenderingProbeVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo

_INTERACTION_CATEGORIES = frozenset({
    'version_switcher',
    'language_switcher',
    'login_gate',
    'tab_panel',
    'expandable_section',
    'client_side_router',
})


def build_rendering_probe(
    http_body_chars: int,
    rendered_body_chars: int,
    *,
    browser_probe_ok: bool = True,
    browser_probe_error: str | None = None,
) -> RenderingProbeVo:
    """根据 HTTP 与渲染后文本量对比，判定渲染模式与空壳风险"""
    ratio = rendered_body_chars / max(http_body_chars, 1)
    mode = _detect_mode(http_body_chars, rendered_body_chars, ratio)
    shell_risk = _detect_shell_risk(http_body_chars, rendered_body_chars, ratio, browser_probe_ok)
    needs_browser = shell_risk in ('medium', 'high') or mode == 'spa'

    return RenderingProbeVo(
        mode=mode,
        http_body_chars=http_body_chars,
        rendered_body_chars=rendered_body_chars,
        content_ratio=round(ratio, 2),
        shell_risk=shell_risk,
        needs_browser=needs_browser,
        browser_probe_ok=browser_probe_ok,
        browser_probe_error=browser_probe_error,
    )


def _detect_mode(http_chars: int, rendered_chars: int, ratio: float) -> str:
    if not rendered_chars and http_chars < 500:
        return 'unknown'
    if http_chars > 5000 and ratio < 2:
        return 'static'
    if http_chars < 2000 and ratio >= 5:
        return 'spa'
    if rendered_chars > http_chars * 2 and http_chars < 3000:
        return 'spa'
    if rendered_chars > 1000:
        return 'ssr'
    return 'unknown'


def _detect_shell_risk(
    http_chars: int,
    rendered_chars: int,
    ratio: float,
    browser_probe_ok: bool,
) -> str:
    if not browser_probe_ok:
        return 'medium'
    if rendered_chars < 200:
        return 'high'
    if http_chars < 500 and ratio >= 3:
        return 'high'
    if 2 <= ratio < 5:
        return 'medium'
    return 'low'


def refine_rendering_for_interactions(
    rendering: RenderingProbeVo,
    url_signals: UrlSignalsVo,
    interactive_elements: list[InteractiveElementVo],
) -> RenderingProbeVo:
    """
    结合交互元素修正渲染判定。

    部分文档站 HTTP 已返回大段 HTML，但版本/语言等仍依赖渲染后 DOM 才能校准；
    此时仅靠 http/rendered 字符比会误判为 static + needs_browser=false。
    """
    categories = {el.category for el in interactive_elements}
    if not categories & _INTERACTION_CATEGORIES:
        return rendering

    updates: dict = {}
    if 'client_side_router' in categories:
        updates['mode'] = 'spa'
        updates['needs_browser'] = True
    elif rendering.mode == 'static' and categories & _INTERACTION_CATEGORIES:
        updates['mode'] = 'hybrid'

    if 'version_switcher' in categories and not url_signals.has_version_in_path:
        updates['needs_browser'] = True
        if rendering.shell_risk == 'low':
            updates['shell_risk'] = 'medium'

    if 'login_gate' in categories or 'captcha' in categories:
        updates['needs_browser'] = True

    if not updates:
        return rendering
    return rendering.model_copy(update=updates)
