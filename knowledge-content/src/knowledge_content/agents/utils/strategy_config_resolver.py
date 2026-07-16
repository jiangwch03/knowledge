"""strategy_config 解析：拆分 browser / crawler_run / hooks"""

from knowledge_content.agents.utils.hook_schema import validate_hooks

# 顶层元数据字段，不属于 crawl4ai 运行参数
_META_KEYS = frozenset({
    'site_type',
    'strategy_summary',
    'needs_user_input',
    'pending_question',
    'hooks',
    'browser_config',
    'crawler_run_config',
})


def resolve_strategy_config(config: dict | None) -> tuple[dict, dict, dict]:
    """
    将 LLM 输出的 strategy_config 拆分为三部分

    :param config: 完整策略配置或扁平 crawler 配置
    :return: (browser_config, crawler_run_config, hooks)
    """
    if not config:
        return {}, {}, {}

    hooks = config.get('hooks') if isinstance(config.get('hooks'), dict) else {}
    validate_hooks(hooks or None)

    browser_config = config.get('browser_config') if isinstance(config.get('browser_config'), dict) else {}

    if isinstance(config.get('crawler_run_config'), dict):
        crawler_run_config = dict(config['crawler_run_config'])
    elif _looks_like_flat_crawler_config(config):
        crawler_run_config = {
            k: v for k, v in config.items()
            if k not in _META_KEYS
        }
    else:
        crawler_run_config = {}

    return browser_config, crawler_run_config, hooks or {}


def merge_hook_params(crawler_run_config: dict, hooks: dict | None) -> dict:
    """将 hooks 转换结果合并进 crawler_run_config（不覆盖已有显式配置）"""
    from knowledge_content.agents.utils.hook_adapter import hooks_to_crawl_params

    merged = dict(crawler_run_config)
    hook_params = hooks_to_crawl_params(hooks)
    for key, value in hook_params.items():
        if key not in merged:
            merged[key] = value
    return merged


def _looks_like_flat_crawler_config(config: dict) -> bool:
    crawler_keys = {
        'deep_crawl_strategy', 'wait_until', 'css_selector', 'page_timeout',
        'cache_mode', 'markdown_generator', 'max_pages',
    }
    return any(k in config for k in crawler_keys)
