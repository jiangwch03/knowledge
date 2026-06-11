"""
BroadcastService 门面

全 @classmethod，提供:
- init(redis): 注入 Redis 客户端，创建后端
- register_subscriber_paths(paths): 业务方声明订阅者所在包路径
- discover_and_start(): 扫描 + 启动后台监听
- publish(channel, payload): 发布消息
- shutdown(): 优雅关闭
- reset(): 单元测试用

所有方法都是 @classmethod，无需也不可以实例化。
"""
from __future__ import annotations

import asyncio
import importlib
import json
import pkgutil
from typing import Any

from redis import asyncio as aioredis

from knowledge_common.broadcast.backends.base import BroadcastBackend
from knowledge_common.broadcast.backends.redis_pubsub import RedisPubSubBackend
from knowledge_common.broadcast.exceptions import BroadcastError
from knowledge_common.broadcast.message import BroadcastMessage
from knowledge_common.broadcast.subscriber import SubscriberInfo
from knowledge_common.utils.log_util import logger


class BroadcastService:
    """
    消息广播服务门面

    业务方:
        from knowledge_common.broadcast import subscriber, BroadcastService

        @subscriber(channel='scheduler:global:sync')
        async def on_sync(msg: BroadcastMessage) -> None: ...

        # 发布
        await BroadcastService.publish('scheduler:global:sync', {'action': 'sync'})
    """

    # 后端实现（由 init 注入）
    _backend: BroadcastBackend | None = None

    # 已注册的订阅者表：{subscriber_id: SubscriberInfo}
    _subscribers: dict[str, SubscriberInfo] = {}

    # 待扫描路径
    _scan_paths: list[str] = ['knowledge_common.message.subscriber',]

    # 是否已启动
    _started: bool = False

    # ==================== 生命周期 ====================

    @classmethod
    def init(cls, redis: aioredis.Redis) -> None:
        """
        注入 Redis 客户端，创建后端实例

        :param redis: aioredis 客户端
        """
        cls._backend = RedisPubSubBackend(redis)
        logger.info('✅ BroadcastService 已初始化')

    @classmethod
    def register_subscriber_paths(cls, paths: list[str]) -> None:
        """
        声明订阅者扫描路径（多次调用幂等累加）

        :param paths: 包路径列表，如 ['knowledge_common.message.subscriber']
        """
        for p in paths:
            if p not in cls._scan_paths:
                cls._scan_paths.append(p)

    @classmethod
    async def discover_and_start(cls) -> None:
        """
        扫描路径触发装饰器注册，为所有已注册订阅者启动后台监听

        :raises BroadcastError: 未调用 init() 时抛出
        """
        if cls._backend is None:
            raise BroadcastError('BroadcastService 未初始化，请先调用 init()')

        if not cls._scan_paths:
            logger.warning('⚠️ BroadcastService: 未注册任何扫描路径，启动 0 个订阅者')
            return

        # 扫描触发 @subscriber 注册
        for path in list(cls._scan_paths):
            cls._import_subtree(path)

        if not cls._subscribers:
            logger.warning('⚠️ BroadcastService: 扫描完成但未发现任何订阅者')
            return

        # 收集所有需订阅的 channel（去重）
        channels = list({info.channel for info in cls._subscribers.values()})

        # 启动后端监听
        await cls._backend.start_listening(channels, cls._dispatch)
        cls._started = True

        logger.info(
            f'✅ BroadcastService 已启动: '
            f'{len(cls._subscribers)} 个订阅者, {len(channels)} 个 channel'
        )

    @classmethod
    async def shutdown(cls) -> None:
        """
        关闭后端连接和监听任务
        """
        if cls._backend:
            await cls._backend.shutdown()
        cls._started = False
        logger.info('🛑 BroadcastService 已关闭')

    @classmethod
    def reset(cls) -> None:
        """
        重置所有状态（单元测试用）
        """
        cls._backend = None
        cls._subscribers = {}
        cls._scan_paths = []
        cls._started = False

    # ==================== 发布 ====================

    @classmethod
    async def publish(cls, channel: str, payload: dict[str, Any] | str) -> int:
        """
        发布广播消息

        :param channel: 目标 channel
        :param payload: 消息载荷，dict 自动 JSON 序列化
        :return: 接收者数量
        :raises BroadcastError: 未初始化时抛出
        """
        if cls._backend is None:
            raise BroadcastError(
                'BroadcastService 未初始化，请先调用 init()',
                channel=channel,
            )

        message = cls._encode_payload(payload)
        return await cls._backend.publish(channel, message)

    # ==================== 内部方法 ====================

    @classmethod
    async def _dispatch(cls, channel: str, data: Any) -> None:
        """
        消息分发：根据 channel 找到对应 handler 列表，逐个调用

        :param channel: 消息来源 channel
        :param data: 已反序列化的 payload
        """
        msg = BroadcastMessage(
            channel=channel,
            payload=data,
            timestamp=asyncio.get_event_loop().time(),
        )

        # 找到所有订阅该 channel 的 handler
        handlers = [
            info.handler
            for info in cls._subscribers.values()
            if info.channel == channel
        ]

        for handler in handlers:
            try:
                await handler(msg)
            except Exception as e:
                logger.error(
                    f'❌ subscriber handler 异常 (channel={channel}): {e}',
                    exc_info=True,
                )

    @classmethod
    def _import_subtree(cls, package_name: str) -> None:
        """
        反射 import 指定包及其子包（触发 @subscriber 装饰器注册）

        :param package_name: 包路径
        """
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error(f'❌ 扫描路径 import 失败: {package_name} err={e}')
            return

        # 确保包有 __path__ 属性（是一个 package）
        if not hasattr(package, '__path__'):
            return

        for _finder, name, is_pkg in pkgutil.iter_modules(package.__path__):
            full_name = f'{package_name}.{name}'
            try:
                importlib.import_module(full_name)
            except ImportError as e:
                logger.error(f'❌ 扫描子模块 import 失败: {full_name} err={e}')
                continue
            if is_pkg:
                cls._import_subtree(full_name)

    @staticmethod
    def _encode_payload(payload: dict[str, Any] | str) -> str | bytes:
        """
        编码发布载荷

        :param payload: dict 自动 JSON 序列化，str 原样返回
        :return: 序列化后的消息
        """
        if isinstance(payload, dict):
            return json.dumps(payload, ensure_ascii=False)
        return payload


__all__ = ['BroadcastService']
