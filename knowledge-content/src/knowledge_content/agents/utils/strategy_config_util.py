"""从 LLM 输出文本中提取 strategy_config JSON"""

from __future__ import annotations

import json
import re
from typing import Annotated, Any

from pydantic import BeforeValidator

from knowledge_common.utils.log_util import logger


def _coerce_crawl_config_to_str(value: Any) -> str | None:
    """工具入参统一成 str：LLM 传 JSON 字符串；兼容误传 dict。"""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError(f'crawl_config 须为 JSON 字符串，实际类型: {type(value).__name__}')


# 暴露给 LLM 的工具入参类型：schema 为 string，同时兼容 dict 误传
CrawlConfigArg = Annotated[str | None, BeforeValidator(_coerce_crawl_config_to_str)]
CrawlConfigArgRequired = Annotated[str, BeforeValidator(_coerce_crawl_config_to_str)]


def parse_tool_crawl_config(crawl_config: str | dict | None) -> dict | None:
    """
    解析工具入参 crawl_config。

    对 LLM 暴露为 JSON 字符串（schema type=string），工具内部转为 dict。
    兼容误传 dict，避免历史调用或中间层二次结构化后直接挂掉。
    """
    if crawl_config is None:
        return None
    if isinstance(crawl_config, dict):
        return crawl_config
    if isinstance(crawl_config, str):
        text = crawl_config.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = extract_json_object(text)
        if not isinstance(parsed, dict):
            raise ValueError('crawl_config 须为 JSON 对象字符串')
        return parsed
    raise ValueError(f'crawl_config 类型非法: {type(crawl_config).__name__}')


def extract_json_object(text: str) -> dict | None:
    """
    从 LLM 回复中提取 JSON 对象

    优先解析 ```json ... ``` 代码块，其次尝试首个 { ... } 子串。
    """
    if not text or not text.strip():
        return None

    fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
    if fence:
        try:
            parsed = json.loads(fence.group(1))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    start = text.find('{')
    if start == -1:
        return None

    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    parsed = json.loads(candidate)
                    return parsed if isinstance(parsed, dict) else None
                except json.JSONDecodeError:
                    logger.debug('[StrategyConfigUtil] JSON 片段解析失败')
                    return None
    return None


# 非 crawl4ai 策略字段（由 Supervisor 侧派生，不得写入 strategy_config）
_STRATEGY_META_KEYS = frozenset({
    'pages_to_remove',
    'scope_summary',
    'strategy_summary',
    'needs_user_input',
    'pending_question',
})


def sanitize_strategy_config(config: dict) -> dict:
    """剥离非策略元数据，仅保留 crawl4ai 策略本体"""
    return {k: v for k, v in config.items() if k not in _STRATEGY_META_KEYS}


def extract_strategy_config(text: str) -> dict | None:
    """提取 crawl4ai 策略配置 JSON（须含 browser_config 或 crawler_run_config）"""
    obj = extract_json_object(text)
    if not obj:
        return None
    if 'browser_config' in obj or 'crawler_run_config' in obj:
        return sanitize_strategy_config(obj)
    return None
