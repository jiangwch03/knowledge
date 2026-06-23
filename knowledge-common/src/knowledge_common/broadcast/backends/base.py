"""
广播后端抽象基类

定义后端必须实现的接口契约，屏蔽 Redis / NATS / RabbitMQ 等协议差异。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable


# 分发函数签名：接收 channel + 原始 payload，由门面负责构造 BroadcastMessage 再调 handler
DispatchFn = Callable[[str, Any], Awaitable[None]]


class BroadcastBackend(ABC):
    """
    广播后端抽象接口

    实现方只需关注：订阅、发布、退订、关闭。
    """

    @abstractmethod
    async def start_listening(self, channels: list[str], dispatch_fn: DispatchFn) -> None:
        """
        订阅指定 channel 列表并启动后台监听

        :param channels: 需订阅的 channel 列表
        :param dispatch_fn: 收到消息时的回调（由 BroadcastService 提供）
        """

    @abstractmethod
    async def add_channel(self, channel: str) -> None:
        """
        动态增量订阅一个 channel（已在 listen 状态下调用）

        :param channel: 新增 channel 名
        """

    @abstractmethod
    async def remove_channel(self, channel: str) -> None:
        """
        动态退订一个 channel

        :param channel: 需退订的 channel 名
        """

    @abstractmethod
    async def publish(self, channel: str, message: str | bytes) -> int:
        """
        发布序列化后的消息

        :param channel: 目标 channel
        :param message: 已序列化的消息内容
        :return: 接收者数量
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """
        关闭所有连接和后台监听任务
        """


__all__ = ['BroadcastBackend', 'DispatchFn']
