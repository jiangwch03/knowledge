"""
@subscriber 装饰器

业务方用 `@subscriber(channel='xxx')` 声明广播消费点，启动时全路径 import 触发注册。
装饰器与门面分开，职责清晰。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from knowledge_common.utils.log_util import logger

# 业务消费函数签名
SubscriberHandler = Callable[["BroadcastMessage"], Awaitable[None]]  # noqa: F821


@dataclass(frozen=True)
class SubscriberInfo:
    """
    已注册订阅者的元信息

    :param subscriber_id: 全局唯一标识（默认 `{module}.{func.__name__}`）
    :param channel: 订阅的 channel 名
    :param handler: 业务 async def(msg: BroadcastMessage) -> None
    """

    subscriber_id: str
    channel: str
    handler: SubscriberHandler


def subscriber(
    channel: str,
    *,
    id: str | None = None,
) -> Callable[[SubscriberHandler], SubscriberHandler]:
    """
    广播订阅者装饰器工厂

    用法:
        @subscriber(channel='scheduler:global:sync')
        async def on_sync(msg: BroadcastMessage) -> None:
            ...

    装饰器立即注册到 BroadcastService._subscribers 表（类级别共享），
    discover_and_start() 时为已注册的 channel 启动后台监听。

    :param channel: 订阅的 channel 名
    :param id: 订阅者唯一 id（默认用 `{module}.{func.__name__}`）
    :return: 装饰器
    """
    # 局部 import 避免循环：service.py 也会被装饰器反向引用
    from knowledge_common.broadcast.service import BroadcastService

    def decorator(func: SubscriberHandler) -> SubscriberHandler:
        subscriber_id = id or f'{func.__module__}.{func.__name__}'

        # 同一 (模块路径, 函数名) 只注册一次，重复装饰跳过
        if subscriber_id in BroadcastService._subscribers:
            logger.debug(
                f'订阅者 {subscriber_id} 已注册，跳过重复装饰'
            )
            return func

        info = SubscriberInfo(
            subscriber_id=subscriber_id,
            channel=channel,
            handler=func,
        )
        BroadcastService._subscribers[subscriber_id] = info
        logger.debug(
            f'✅ 订阅者已注册: id={subscriber_id} channel={channel}'
        )
        return func

    return decorator


__all__ = ['subscriber', 'SubscriberInfo', 'SubscriberHandler']
