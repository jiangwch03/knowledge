"""从 Agent runtime.context（dict / Pydantic）安全取值。"""

from __future__ import annotations

from typing import Any


def context_as_dict(context: Any) -> dict[str, Any]:
    """把 runtime.context 规范成 dict；无法识别时返回空 dict。"""
    if context is None:
        return {}
    if hasattr(context, 'model_dump'):
        dumped = context.model_dump()
        return dumped if isinstance(dumped, dict) else {}
    if isinstance(context, dict):
        return context
    return {}


def context_get(context: Any, key: str, default: Any = None) -> Any:
    return context_as_dict(context).get(key, default)


def context_get_int(context: Any, key: str) -> int | None:
    """解析整型字段；缺失 / 空串 / 非法值返回 None。"""
    value = context_get(context, key)
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def runtime_ctx_int(runtime: Any, key: str) -> int | None:
    """从 Runtime.context 取整型字段。"""
    return context_get_int(getattr(runtime, 'context', None), key)
