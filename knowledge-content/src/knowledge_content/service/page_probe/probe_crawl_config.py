"""将 cookies 字符串转为探针/试爬可用的 hooks evaluate 步骤"""

from __future__ import annotations


def cookies_to_hook_step(cookies: str) -> dict:
    """
    把 Cookie 头字符串注入页面（非 HttpOnly cookie）。

    :param cookies: 如 ``session=abc; token=xyz``
    """
    normalized = (cookies or '').strip()
    if not normalized:
        return {}
    escaped = normalized.replace('\\', '\\\\').replace("'", "\\'")
    code = (
        "(() => {"
        f" const raw = '{escaped}';"
        " raw.split(';').forEach(part => {"
        "   const p = part.trim();"
        "   if (p) document.cookie = p;"
        " });"
        "})();"
    )
    return {'type': 'evaluate', 'code': code}


def build_probe_crawl_config(
    *,
    hooks: dict | None = None,
    cookies: str | None = None,
) -> dict | None:
    """组装探针可选的 crawl_config（hooks + cookie 注入）"""
    merged_hooks: dict = dict(hooks) if hooks else {}
    cookie_step = cookies_to_hook_step(cookies) if cookies else {}
    if cookie_step:
        actions = list(merged_hooks.get('on_page_loaded') or [])
        if actions:
            first = dict(actions[0])
            steps = [cookie_step, *(first.get('steps') or [])]
            first['steps'] = steps
            actions[0] = first
        else:
            actions = [{'action': 'inject_cookies', 'steps': [cookie_step]}]
        merged_hooks['on_page_loaded'] = actions

    if not merged_hooks:
        return None
    return {'hooks': merged_hooks}
