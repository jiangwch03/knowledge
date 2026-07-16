"""探针访问守卫：登录重定向 / 验证码等阻断场景的检测与短路"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.rendered_page_probe_vo import RenderedPageProbeVo

_LOGIN_PATH_RE = re.compile(r'/(?:login|signin|sign-in|auth/login)(?:/|$|\?)', re.IGNORECASE)
_REDIRECT_QUERY_KEYS = ('redirect', 'returnUrl', 'return_url', 'next', 'callback', 'continue')


def parse_intended_url(request_url: str, actual_url: str | None) -> str | None:
    """从登录页 redirect 查询参数还原用户意图 URL"""
    if not actual_url:
        return None
    parsed = urlparse(actual_url)
    qs = parse_qs(parsed.query)
    for key in _REDIRECT_QUERY_KEYS:
        values = qs.get(key)
        if not values:
            continue
        raw = (values[0] or '').strip()
        if not raw:
            continue
        if raw.startswith(('http://', 'https://')):
            return raw
        if raw.startswith('/'):
            return f'{parsed.scheme}://{parsed.netloc}{raw}'
        return urljoin(request_url, raw)
    return None


def is_login_url(url: str) -> bool:
    if not url:
        return False
    return bool(_LOGIN_PATH_RE.search(urlparse(url).path))


def _has_captcha(elements: list[InteractiveElementVo]) -> bool:
    if any(el.category == 'captcha' for el in elements):
        return True
    login_el = next((el for el in elements if el.category == 'login_gate'), None)
    if login_el and any(f.role == 'captcha' for f in login_el.fields):
        return True
    return False


def detect_probe_block(
    request_url: str,
    actual_url: str | None,
    interactive_elements: list[InteractiveElementVo],
    *,
    auth_injected: bool = False,
) -> tuple[str | None, str | None]:
    """
  检测探针是否被登录/验证码阻断。

  :return: (block_reason, intended_url)；无阻断时 (None, None)
  """
    if auth_injected:
        return None, None

    categories = {el.category for el in interactive_elements}
    intended = parse_intended_url(request_url, actual_url)

    if actual_url and is_login_url(actual_url) and not is_login_url(request_url):
        return 'login_redirect', intended or request_url

    if 'login_gate' in categories or 'login_prompt' in categories:
        return 'login_required', intended or request_url

    if _has_captcha(interactive_elements):
        return 'captcha_required', intended or request_url

    return None, None


def apply_probe_block_short_circuit(vo: RenderedPageProbeVo) -> RenderedPageProbeVo:
    """登录/验证码阻断时短路：保留写 hook 所需字段，清空对目标页无效的分析层"""
    login_elements = [
        el for el in vo.interactive_elements
        if el.category in {'login_gate', 'login_prompt', 'captcha'}
    ]
    blocked_controls = [
        c for c in vo.controls
        if c.control_type == 'password'
        or c.control_type in ('text', 'email', 'tel', '')
        or (c.tag == 'button' and '登录' in (c.text or ''))
    ] if login_elements else []

    implications = [
        'probe_target_unreachable',
        'stop_probe_use_trial_after_auth',
    ]
    if vo.block_reason == 'login_redirect':
        implications.append('redirected_to_login')
    if vo.block_reason in ('login_redirect', 'login_required'):
        implications.extend(['ask_user_for_credentials', 'login_form_fields_detected'])
    if vo.block_reason == 'captcha_required' or _has_captcha(login_elements):
        implications.append('blocked_without_captcha')

    # 去重且保留顺序
    implications = list(dict.fromkeys(implications + [
        imp for imp in vo.crawl_implications
        if imp in {
            'ask_user_for_credentials',
            'login_form_fields_detected',
            'login_required_for_full_content',
            'blocked_without_captcha',
        }
    ]))

    return vo.model_copy(update={
        'probe_status': 'blocked',
        'action_required': 'ask_user_then_trial_with_hooks',
        'interactive_elements': login_elements,
        'controls': blocked_controls or vo.controls[:6],
        'site_type_candidates': [],
        'version_url_patterns': [],
        'crawl_implications': implications,
    })
