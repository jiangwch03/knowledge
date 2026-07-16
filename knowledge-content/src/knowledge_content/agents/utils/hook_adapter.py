"""将 hooks steps 转换为 crawl4ai js_code / wait_for"""

from knowledge_content.agents.utils.hook_schema import validate_hooks

# 页面加载后执行的 hook 阶段（映射到 js_code_before_wait）
_PAGE_HOOK_PHASES = ('on_page_loaded', 'on_before_request', 'on_after_page_load')


def hooks_to_crawl_params(hooks: dict | None) -> dict:
    """
    将 hooks 声明转换为 crawl4ai CrawlerRunConfig 可接受的参数

    :param hooks: strategy_config.hooks
    :return: 含 js_code_before_wait / wait_for 的 dict（可能为空）
    """
    if not hooks:
        return {}

    validate_hooks(hooks)

    js_snippets: list[str] = []
    wait_for: str | None = None

    for phase in _PAGE_HOOK_PHASES:
        for action in hooks.get(phase) or []:
            for step in action.get('steps') or []:
                snippet = _step_to_js(step)
                if snippet:
                    js_snippets.append(snippet)
                wait_selector = _step_to_wait_for(step)
                if wait_selector:
                    wait_for = wait_selector

    result: dict = {}
    if js_snippets:
        result['js_code_before_wait'] = js_snippets
    if wait_for:
        result['wait_for'] = wait_for
    return result


def _step_to_js(step: dict) -> str | None:
    step_type = step.get('type')
    selector = step.get('selector', '')

    if step_type == 'evaluate':
        code = step.get('code') or step.get('value') or ''
        return code.strip() or None

    if step_type == 'click':
        return _click_js(selector)

    if step_type == 'fill':
        value = (step.get('value') or '').replace('\\', '\\\\').replace("'", "\\'")
        return f"(() => {{ const el = {_selector_expr(selector)}; if (el) el.value = '{value}'; }})();"

    return None


def _step_to_wait_for(step: dict) -> str | None:
    if step.get('type') != 'wait':
        return None
    selector = step.get('selector', '').strip()
    if not selector:
        return None
    if selector.startswith('css:') or selector.startswith('js:'):
        return selector
    return f'css:{selector}'


def _click_js(selector: str) -> str:
    if selector.startswith('text='):
        text = selector[5:].replace('\\', '\\\\').replace("'", "\\'")
        return (
            f"(() => {{ const t = '{text}'; "
            "const el = Array.from(document.querySelectorAll('button,a,li,span,div,option'))"
            ".find(n => (n.textContent || '').trim().includes(t)); "
            "if (el) el.click(); })();"
        )
    return f"(() => {{ const el = {_selector_expr(selector)}; if (el) el.click(); }})();"


def _selector_expr(selector: str) -> str:
    safe = selector.replace('\\', '\\\\').replace("'", "\\'")
    return f"document.querySelector('{safe}')"
