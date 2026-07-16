"""
③ 交互归类：将控件列表 + 页面事实归纳为 interactive_elements。

只输出 DOM 事实与分类，不生成 hooks；Planning Agent 据此推理策略。
"""

from __future__ import annotations

import re

from knowledge_content.service.vo.interactive_element_vo import (
    ControlFieldVo,
    InteractiveElementVo,
    SubmitControlVo,
)
from knowledge_content.service.vo.page_control_vo import PageControlVo
from knowledge_content.service.vo.page_structure_vo import PageStructureVo

_VERSION_TEXT_RE = re.compile(r'\bv\d+(?:\.\d+){0,2}(?:\.x)?\b', re.IGNORECASE)
_SEARCH_HINT_RE = re.compile(r'搜索|search|query|查找', re.IGNORECASE)
_PAGINATION_TEXT_RE = re.compile(
    r'下一页|上一页|next|prev|previous|load\s*more|加载更多|查看更多',
    re.IGNORECASE,
)
_LOGIN_TEXT_RE = re.compile(r'登录|登入|sign\s*in|log\s*in', re.IGNORECASE)
_USERNAME_HINT_RE = re.compile(r'账号|用户名|user\s*name|email|手机', re.IGNORECASE)
_CAPTCHA_HINT_RE = re.compile(r'验证码|captcha|code', re.IGNORECASE)


def classify_interactions(
    html: str,
    visible_text: str,
    controls: list[PageControlVo],
    page_structure: PageStructureVo,
    nav_link_count: int = 0,
) -> list[InteractiveElementVo]:
    """主入口：汇总各类交互元素"""
    elements: list[InteractiveElementVo] = []
    used_categories: set[str] = set()

    login_el = _classify_login_gate(controls)
    if login_el:
        elements.append(login_el)
        used_categories.add('login_gate')

    if 'login_gate' not in used_categories:
        search_el = _classify_search_box(controls, html)
        if search_el:
            elements.append(search_el)
            used_categories.add('search_box')

    pagination_el = _classify_pagination(controls, html, visible_text)
    if pagination_el:
        elements.append(pagination_el)

    filter_el = _classify_filter_panel(controls, html)
    if filter_el:
        elements.append(filter_el)

    category_el = _classify_category_navigation(html, visible_text, page_structure)
    if category_el:
        elements.append(category_el)

    elements.extend(_classify_from_html_patterns(
        html, visible_text, nav_link_count, skip_login='login_gate' in used_categories,
    ))
    return _dedupe_by_category(elements)


def _classify_login_gate(controls: list[PageControlVo]) -> InteractiveElementVo | None:
    password_inputs = [c for c in controls if c.control_type == 'password']
    if not password_inputs:
        return None

    text_inputs = [
        c for c in controls
        if c.tag == 'input' and c.control_type in ('text', 'email', 'tel', '')
    ]
    buttons = [c for c in controls if c.tag == 'button']

    fields: list[ControlFieldVo] = []
    for inp in text_inputs:
        role = 'username'
        hint = f'{inp.placeholder} {inp.name} {inp.aria_label}'.lower()
        if _CAPTCHA_HINT_RE.search(hint):
            role = 'captcha'
        elif _USERNAME_HINT_RE.search(hint) or inp.control_type in ('email', 'tel'):
            role = 'username'
        elif len(text_inputs) == 1:
            role = 'username'
        else:
            role = 'unknown'
        fields.append(ControlFieldVo(
            role=role,
            selector=inp.selector,
            control_type=inp.control_type,
            placeholder=inp.placeholder,
        ))

    for pwd in password_inputs:
        fields.append(ControlFieldVo(
            role='password',
            selector=pwd.selector,
            control_type='password',
            placeholder=pwd.placeholder,
        ))

    submit_btn = None
    for btn in buttons:
        if _LOGIN_TEXT_RE.search(btn.text) or 'primary' in btn.selector:
            submit_btn = SubmitControlVo(selector=btn.selector, text=btn.text)
            break
    if not submit_btn and buttons:
        submit_btn = SubmitControlVo(selector=buttons[0].selector, text=buttons[0].text)

    has_captcha = any(f.role == 'captcha' for f in fields)
    return InteractiveElementVo(
        category='login_gate',
        confidence=0.85 if fields else 0.7,
        location='main',
        evidence=['存在 password 输入框'] + ([f'含验证码字段'] if has_captcha else []),
        impact='blocked_without_auth',
        trigger_mode='form_submit',
        fields=fields,
        submit=submit_btn,
    )


def _classify_search_box(controls: list[PageControlVo], html: str) -> InteractiveElementVo | None:
    candidates = [
        c for c in controls
        if c.tag == 'input'
        and (
            c.control_type == 'search'
            or _SEARCH_HINT_RE.search(f'{c.placeholder} {c.name} {c.aria_label}')
            or (c.tag == 'input' and 'search' in html.lower() and c.control_type == 'text')
        )
    ]
    if not candidates:
        # role=search 或 type=search 在 html 里但未被 input 正则捕获时
        if not re.search(r'type=["\']search["\']|role=["\']search["\']', html, re.I):
            return None
        candidates = [PageControlVo(tag='input', control_type='search', selector='input[type="search"]')]

    field = candidates[0]
    buttons = [c for c in controls if c.tag == 'button' and _SEARCH_HINT_RE.search(c.text)]
    trigger = 'instant' if not buttons else 'submit_on_button'
    submit = SubmitControlVo(selector=buttons[0].selector, text=buttons[0].text) if buttons else None

    return InteractiveElementVo(
        category='search_box',
        confidence=0.75,
        location='header' if 'header' in html.lower()[:3000] else 'unknown',
        evidence=[f'搜索输入: {field.placeholder or field.selector}'],
        impact='search_scope_may_be_required',
        trigger_mode=trigger,
        fields=[ControlFieldVo(
            role='search_query',
            selector=field.selector,
            control_type=field.control_type,
            placeholder=field.placeholder,
        )],
        submit=submit,
    )


def _classify_pagination(
    controls: list[PageControlVo],
    html: str,
    visible_text: str,
) -> InteractiveElementVo | None:
    mode = ''
    evidence: list[str] = []
    submit = None

    if re.search(r'load\s*more|加载更多|查看更多', visible_text, re.I):
        mode = 'load_more'
        evidence.append('可见「加载更多」类文案')
    elif re.search(r'无限滚动|infinite\s*scroll', html, re.I):
        mode = 'infinite_scroll'
        evidence.append('页面含无限滚动相关结构/文案')
    elif re.search(r'pagination|el-pagination|page-item|下一页|next', html, re.I):
        mode = 'numbered'
        evidence.append('存在分页组件或翻页文案')

    for btn in controls:
        if btn.tag == 'button' and _PAGINATION_TEXT_RE.search(btn.text):
            submit = SubmitControlVo(selector=btn.selector, text=btn.text)
            if not mode:
                mode = 'load_more' if '更多' in btn.text else 'numbered'
            break

    if not mode:
        return None

    return InteractiveElementVo(
        category='pagination',
        confidence=0.7,
        location='main',
        evidence=evidence,
        impact='multi_page_content',
        mode=mode,
        submit=submit,
    )


def _classify_filter_panel(controls: list[PageControlVo], html: str) -> InteractiveElementVo | None:
    """筛选面板须至少有真实 select 控件，禁止仅凭 HTML 文案误报"""
    selects = [c for c in controls if c.tag == 'select' and len(c.options) >= 2]
    if len(selects) < 1:
        return None

    filters: list[ControlFieldVo] = []
    for sel in selects:
        filters.append(ControlFieldVo(
            role='filter',
            selector=sel.selector,
            control_type='select',
            options=sel.options,
        ))

    query_btn = next(
        (c for c in controls if c.tag == 'button' and re.search(r'查询|筛选|搜索|apply|filter', c.text, re.I)),
        None,
    )
    trigger = 'manual_query' if query_btn else 'instant'

    return InteractiveElementVo(
        category='filter_panel',
        confidence=0.65 if len(selects) >= 2 else 0.6,
        location='main',
        evidence=[f'筛选下拉 {len(selects)} 个'],
        impact='filter_combination_explosion',
        trigger_mode=trigger,
        filters=filters,
        submit=SubmitControlVo(selector=query_btn.selector, text=query_btn.text) if query_btn else None,
    )


def _classify_category_navigation(
    html: str,
    visible_text: str,
    page_structure: PageStructureVo,
) -> InteractiveElementVo | None:
    from knowledge_content.service.page_probe.category_navigation_detector import detect_category_navigation

    return detect_category_navigation(html, visible_text, page_structure)


def _classify_from_html_patterns(
    html: str,
    visible_text: str,
    nav_link_count: int,
    *,
    skip_login: bool,
) -> list[InteractiveElementVo]:
    """保留基于 HTML 模式的检测（版本/语言/cookie 等），与控件提取互补"""
    from knowledge_content.service.page_probe import interactive_element_classifier as legacy

    raw = legacy.classify_interactive_elements(html, visible_text, nav_link_count)
    skip = {'login_gate'} if skip_login else set()
    return [el for el in raw if el.category not in skip]


def _dedupe_by_category(elements: list[InteractiveElementVo]) -> list[InteractiveElementVo]:
    seen: set[str] = set()
    out: list[InteractiveElementVo] = []
    for el in elements:
        if el.category in seen:
            continue
        seen.add(el.category)
        out.append(el)
    return out
