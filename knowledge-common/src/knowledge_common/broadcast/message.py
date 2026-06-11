"""
广播消息数据类

handler 接收的统一消息结构，隔离底层实现细节。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BroadcastMessage:
    """
    广播消息 DTO

    :param channel: 消息来源 channel
    :param payload: 自动 JSON 反序列化后的载荷（dict 或原始 str）
    :param timestamp: 消息接收时间戳（event loop 时间）
    """

    channel: str
    payload: dict[str, Any] | str
    timestamp: float

    def __repr__(self) -> str:
        return f'<BroadcastMessage channel={self.channel!r} payload={self.payload!r}>'


__all__ = ['BroadcastMessage']
