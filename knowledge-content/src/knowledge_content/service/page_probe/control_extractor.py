"""
② 控件提取：从渲染后 HTML 批量抽取 input/button/select/textarea。

站点无关规则，不判断业务语义；语义归类在 interaction_classifier。
"""

from __future__ import annotations

import re

from knowledge_content.service.vo.page_control_vo import PageControlVo

_INPUT_RE = re.compile(r'<input([^>]*)/?>', re.IGNORECASE)
_BUTTON_RE = re.compile(r'<button([^>]*)>(.*?)</button>', re.DOTALL | re.IGNORECASE)
_SELECT_RE = re.compile(r'<select([^>]*)>(.*?)</select>', re.DOTALL | re.IGNORECASE)
_TEXTAREA_RE = re.compile(r'<textarea([^>]*)>', re.IGNORECASE)


def extract_page_controls(html: str) -> list[PageControlVo]:
    """扫描 HTML 中所有可交互控件"""
    if not html:
        return []

    controls: list[PageControlVo] = []
    seen: set[str] = set()

    for m in _INPUT_RE.finditer(html):
        attrs = m.group(1)
        ctrl = _parse_input(attrs)
        if ctrl and ctrl.selector not in seen:
            seen.add(ctrl.selector)
            controls.append(ctrl)

    for m in _BUTTON_RE.finditer(html):
        attrs, inner = m.group(1), m.group(2)
        ctrl = _parse_button(attrs, inner)
        if ctrl and ctrl.selector not in seen:
            seen.add(ctrl.selector)
            controls.append(ctrl)

    for m in _SELECT_RE.finditer(html):
        attrs, body = m.group(1), m.group(2)
        ctrl = _parse_select(attrs, body)
        if ctrl and ctrl.selector not in seen:
            seen.add(ctrl.selector)
            controls.append(ctrl)

    for m in _TEXTAREA_RE.finditer(html):
        attrs = m.group(1)
        ctrl = _parse_textarea(attrs)
        if ctrl and ctrl.selector not in seen:
            seen.add(ctrl.selector)
            controls.append(ctrl)

    return controls


def _attr(attrs: str, name: str) -> str:
    m = re.search(rf'{name}=["\']([^"\']*)["\']', attrs, re.IGNORECASE)
    return (m.group(1) if m else '').strip()


def _best_selector(
    tag: str,
    *,
    control_type: str = '',
    placeholder: str = '',
    name: str = '',
    control_id: str = '',
    text: str = '',
) -> str:
    """生成相对稳定、可供 Agent 写 hook 的 CSS selector"""
    if placeholder:
        return f'{tag}[placeholder="{placeholder}"]'
    if name:
        return f'{tag}[name="{name}"]'
    if control_type and tag == 'input':
        return f'input[type="{control_type}"]'
    if text and tag == 'button':
        safe = text.replace('\\', '\\\\').replace('"', '\\"')[:40]
        return f'button:has-text("{safe}")'  # 文档用；hook_adapter 用 text= 语法
    if control_id and not re.match(r'^el-id-\d+', control_id):
        return f'#{control_id}'
    if control_type:
        return f'{tag}[type="{control_type}"]'
    return tag


def _parse_input(attrs: str) -> PageControlVo | None:
    control_type = (_attr(attrs, 'type') or 'text').lower()
    if control_type in ('hidden', 'submit', 'button', 'image', 'file'):
        return None
    placeholder = _attr(attrs, 'placeholder')
    name = _attr(attrs, 'name')
    control_id = _attr(attrs, 'id')
    aria = _attr(attrs, 'aria-label')
    return PageControlVo(
        tag='input',
        control_type=control_type,
        placeholder=placeholder,
        name=name,
        control_id=control_id,
        aria_label=aria,
        selector=_best_selector(
            'input', control_type=control_type, placeholder=placeholder,
            name=name, control_id=control_id,
        ),
    )


def _parse_button(attrs: str, inner: str) -> PageControlVo | None:
    text = re.sub(r'<[^>]+>', '', inner).strip()
    if not text:
        text = _attr(attrs, 'aria-label')
    control_type = _attr(attrs, 'type') or 'button'
    control_id = _attr(attrs, 'id')
    classes = _attr(attrs, 'class')
    selector = _best_selector('button', text=text, control_id=control_id)
    if 'el-button--primary' in classes:
        selector = 'button.el-button--primary'
    elif text:
        selector = f'button'  # Agent 用 text= 更稳；保留 tag 级 fallback
    return PageControlVo(
        tag='button',
        control_type=control_type,
        text=text[:80],
        control_id=control_id,
        selector=selector,
    )


def _parse_select(attrs: str, body: str) -> PageControlVo | None:
    name = _attr(attrs, 'name')
    control_id = _attr(attrs, 'id')
    options = [
        re.sub(r'<[^>]+>', '', t).strip()
        for t in re.findall(r'<option[^>]*>([^<]*)</option>', body, re.I)
        if t.strip()
    ]
    if not options:
        return None
    return PageControlVo(
        tag='select',
        control_type='select',
        name=name,
        control_id=control_id,
        options=options[:20],
        selector=_best_selector('select', name=name, control_id=control_id),
    )


def _parse_textarea(attrs: str) -> PageControlVo | None:
    placeholder = _attr(attrs, 'placeholder')
    name = _attr(attrs, 'name')
    return PageControlVo(
        tag='textarea',
        control_type='textarea',
        placeholder=placeholder,
        name=name,
        control_id=_attr(attrs, 'id'),
        selector=_best_selector('textarea', placeholder=placeholder, name=name),
    )
