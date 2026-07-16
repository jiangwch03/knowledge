"""从渲染后 HTML / 文本中分类交互元素（站点无关启发式）"""

import re

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.page_probe.version_signal_util import detect_version_switcher_signal

_LANGUAGE_HREF_RE = re.compile(
    r'href=["\'][^"\']*/(?:zh|en|ja|ko|fr|de|es)(?:[-/]|["\'])',
    re.IGNORECASE,
)


def classify_interactive_elements(
    html: str,
    visible_text: str,
    nav_link_count: int = 0,
) -> list[InteractiveElementVo]:
    """基于渲染后 HTML 与可见文本，输出交互元素分类列表"""
    elements: list[InteractiveElementVo] = []
    combined = f'{html}\n{visible_text}'

    _maybe_add_version_switcher(elements, html, visible_text)
    _maybe_add_language_switcher(elements, html, combined)
    _maybe_add_cookie_consent(elements, combined)
    _maybe_add_login_gate(elements, html, combined)
    _maybe_add_login_prompt(elements, html, combined)
    _maybe_add_captcha(elements, html)
    _maybe_add_tab_panel(elements, html)
    _maybe_add_sidebar_nav(elements, nav_link_count)
    _maybe_add_client_router(elements, html)

    return elements


def _maybe_add_version_switcher(
    elements: list[InteractiveElementVo],
    html: str,
    visible_text: str,
) -> None:
    """文档版本选择器：委托站点无关探测（select / ARIA listbox / 链接簇 / 触发器）。"""
    signal = detect_version_switcher_signal(html, visible_text)
    if not signal:
        return
    elements.append(InteractiveElementVo(
        category='version_switcher',
        confidence=signal.confidence,
        location=signal.location,
        evidence=signal.evidence,
        current_value=signal.current_value,
        options=signal.options,
        impact='wrong_version_without_interaction',
    ))


def _maybe_add_login_prompt(elements: list[InteractiveElementVo], html: str, combined: str) -> None:
    """
    软登录门：无 password 表单，但有「登录后查看」类引导（知乎知学堂等）。
    与 login_gate（硬表单）区分。
    """
    has_password = bool(re.search(r'type=["\']password["\']', html, re.IGNORECASE))
    if has_password:
        return
    prompt_patterns = [
        r'立即登录',
        r'登录后(?:可)?查看',
        r'登录(?:后)?(?:才能|方可)',
        r'sign\s+in\s+to\s+(?:view|access)',
        r'log\s+in\s+to\s+(?:view|access)',
    ]
    matched = [p for p in prompt_patterns if re.search(p, combined, re.IGNORECASE)]
    if not matched and not re.search(r'登录', combined):
        return
    elements.append(InteractiveElementVo(
        category='login_prompt',
        confidence=0.7,
        location='main',
        evidence=['页面含登录引导文案，无当前页登录表单'] + matched[:2],
        impact='content_limited_without_auth',
    ))


def _maybe_add_language_switcher(
    elements: list[InteractiveElementVo],
    html: str,
    combined: str,
) -> None:
    evidence: list[str] = []
    options: list[str] = []

    if 'hreflang' in html.lower():
        evidence.append('存在 hreflang 标签')
    lang_hrefs = _LANGUAGE_HREF_RE.findall(html)
    if lang_hrefs:
        evidence.append(f'多语言链接 {len(lang_hrefs)} 个')
        for href in lang_hrefs[:5]:
            m = re.search(r'/(zh|en|ja|ko|fr|de|es)', href, re.IGNORECASE)
            if m and m.group(1) not in options:
                options.append(m.group(1).lower())

    if len(options) < 2 and not evidence:
        return

    elements.append(InteractiveElementVo(
        category='language_switcher',
        confidence=0.75 if len(options) >= 2 else 0.55,
        location='header',
        evidence=evidence,
        options=options[:10],
        impact='wrong_language_without_filter',
    ))


def _maybe_add_cookie_consent(elements: list[InteractiveElementVo], combined: str) -> None:
    if not re.search(r'cookie|consent|accept all|同意', combined, re.IGNORECASE):
        return
    elements.append(InteractiveElementVo(
        category='cookie_consent',
        confidence=0.6,
        location='main',
        evidence=['页面含 cookie/consent 相关文案'],
        impact='content_obscured',
    ))


def _maybe_add_login_gate(elements: list[InteractiveElementVo], html: str, combined: str) -> None:
    has_password = bool(re.search(r'type=["\']password["\']', html, re.IGNORECASE))
    has_login_text = bool(re.search(r'\b(?:login|sign\s*in|登录|登入)\b', combined, re.IGNORECASE))
    if not (has_password and has_login_text):
        return
    elements.append(InteractiveElementVo(
        category='login_gate',
        confidence=0.8,
        location='main',
        evidence=['存在密码输入框与登录文案'],
        impact='blocked_without_auth',
    ))


def _maybe_add_captcha(elements: list[InteractiveElementVo], html: str) -> None:
    if not re.search(r'recaptcha|hcaptcha|captcha', html, re.IGNORECASE):
        return
    elements.append(InteractiveElementVo(
        category='captcha',
        confidence=0.85,
        location='main',
        evidence=['检测到验证码组件'],
        impact='blocked_without_captcha',
    ))


def _maybe_add_tab_panel(elements: list[InteractiveElementVo], html: str) -> None:
    if not re.search(r'role=["\']tablist["\']|role=["\']tab["\']', html, re.IGNORECASE):
        return
    elements.append(InteractiveElementVo(
        category='tab_panel',
        confidence=0.7,
        location='main',
        evidence=['存在 tab 切换结构'],
        impact='partial_content_without_expand',
    ))


def _maybe_add_sidebar_nav(elements: list[InteractiveElementVo], nav_link_count: int) -> None:
    if nav_link_count < 15:
        return
    elements.append(InteractiveElementVo(
        category='sidebar_navigation',
        confidence=0.8,
        location='sidebar',
        evidence=[f'侧边导航链接约 {nav_link_count} 个'],
        impact='urls_may_need_render_first',
    ))


def _maybe_add_client_router(elements: list[InteractiveElementVo], html: str) -> None:
    void_links = len(re.findall(
        r'href=["\'](?:#|javascript:void\s*\(?0?\)?)',
        html,
        re.IGNORECASE,
    ))
    if void_links < 2:
        return
    elements.append(InteractiveElementVo(
        category='client_side_router',
        confidence=0.65 if void_links < 5 else 0.8,
        location='unknown',
        evidence=[f'前端 void/hash 路由链接约 {void_links} 个'],
        impact='urls_not_in_html',
    ))
