"""Agent state.messages 中取本轮用户消息的公共方法。"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage


def last_human_message(state: dict[str, Any]) -> Any | None:
    """取 messages 最后一条；是用户消息则返回，否则 None。"""
    messages = state.get('messages') or []
    if not messages:
        return None
    msg = messages[-1]
    if isinstance(msg, HumanMessage) or getattr(msg, 'type', None) == 'human':
        return msg
    if isinstance(msg, dict) and (
        msg.get('role') in ('user', 'human') or msg.get('type') == 'human'
    ):
        return msg
    return None


def message_text(msg: Any | None) -> str:
    """提取消息文本内容；非字符串 / 空则返回 ''。"""
    if msg is None:
        return ''
    if isinstance(msg, dict):
        return str(msg.get('content') or '').strip()
    content = getattr(msg, 'content', None)
    return content.strip() if isinstance(content, str) else ''


def last_human_text(state: dict[str, Any]) -> str:
    """取 messages 最后一条用户消息的文本；否则 ''。"""
    return message_text(last_human_message(state))
