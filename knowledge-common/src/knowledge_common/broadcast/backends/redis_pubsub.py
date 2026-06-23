"""
Redis Pub/Sub 后端实现

单 pubsub 连接 + dispatch table 多路分发:
- 一个 redis.pubsub() 对象订阅所有 channel
- 一个后台 Task 驱动 listen loop
- 自动重连 + handler 异常隔离
"""
from __future__ import annotations

import asyncio
import json

from redis import asyncio as aioredis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)

from knowledge_common.broadcast.backends.base import BroadcastBackend, DispatchFn
from knowledge_common.utils.log_util import logger

# 重连间隔（秒）
_RETRY_INTERVAL: float = 5.0


class RedisPubSubBackend(BroadcastBackend):
    """
    基于 Redis Pub/Sub 的广播后端

    采用单连接多路分发架构：
    - 一个共享 pubsub 对象
    - 一个后台 listen Task
    - 通过 dispatch_fn 回调将消息按 channel 路由到上层 handler
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self._redis = redis
        self._pubsub: aioredis.client.PubSub | None = None
        self._listen_task: asyncio.Task | None = None
        self._dispatch_fn: DispatchFn | None = None
        self._channels: set[str] = set()
        self._running: bool = False

    async def start_listening(self, channels: list[str], dispatch_fn: DispatchFn) -> None:
        """
        订阅 channel 列表并启动后台监听

        :param channels: 需订阅的 channel 列表
        :param dispatch_fn: 消息分发回调
        """
        self._dispatch_fn = dispatch_fn
        self._channels = set(channels)

        if not self._channels:
            logger.warning('⚠️ BroadcastBackend: 无 channel 需订阅，跳过启动')
            return

        self._running = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info(f'✅ BroadcastBackend 已启动，订阅 {len(self._channels)} 个 channel')

    async def add_channel(self, channel: str) -> None:
        """
        动态增量订阅 channel

        :param channel: 新增 channel 名
        """
        if channel in self._channels:
            return
        self._channels.add(channel)
        if self._pubsub and self._running:
            try:
                await self._pubsub.subscribe(channel)
                logger.info(f'✅ 动态订阅: {channel}')
            except Exception as e:
                logger.error(f'❌ 动态订阅失败: {channel} err={e}')

    async def remove_channel(self, channel: str) -> None:
        """
        动态退订 channel

        :param channel: 需退订的 channel 名
        """
        self._channels.discard(channel)
        if self._pubsub and self._running:
            try:
                await self._pubsub.unsubscribe(channel)
                logger.info(f'🛑 动态退订: {channel}')
            except Exception:
                pass

    async def publish(self, channel: str, message: str | bytes) -> int:
        """
        发布消息

        :param channel: 目标 channel
        :param message: 已序列化的消息
        :return: 接收者数量
        """
        n = await self._redis.publish(channel, message)
        logger.info(f'📢 广播发布 [{channel}]: 接收者={n}')
        return n

    async def shutdown(self) -> None:
        """
        关闭监听任务和 pubsub 连接
        """
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None
        logger.info('🛑 BroadcastBackend 已关闭')

    # ==================== 内部实现 ====================

    async def _listen_loop(self) -> None:
        """
        双层循环：
        - 外层 while True：异常时重连
        - 内层 async for listen()：阻塞读取 + dispatch
        """
        while self._running:
            self._pubsub = self._redis.pubsub()
            try:
                # 批量订阅所有已注册 channel
                if self._channels:
                    await self._pubsub.subscribe(*self._channels)
                    logger.info(
                        f'✅ Pub/Sub 订阅成功: {sorted(self._channels)}'
                    )

                async for raw_message in self._pubsub.listen():
                    if not self._running:
                        break
                    if raw_message.get('type') != 'message':
                        continue
                    await self._handle_raw_message(raw_message)

            except asyncio.CancelledError:
                # 主动取消（应用关闭）
                break
            except (RedisConnectionError, RedisTimeoutError) as e:
                logger.warning(
                    f'⚠️ Pub/Sub 连接异常: {e}，{_RETRY_INTERVAL}s 后重连'
                )
                await self._safe_close_pubsub()
                await asyncio.sleep(_RETRY_INTERVAL)
            except Exception as e:
                logger.error(
                    f'❌ Pub/Sub 异常: {e}，{_RETRY_INTERVAL}s 后重连',
                    exc_info=True,
                )
                await self._safe_close_pubsub()
                await asyncio.sleep(_RETRY_INTERVAL)

        await self._safe_close_pubsub()

    async def _handle_raw_message(self, raw: dict) -> None:
        """
        解析并分发单条消息

        :param raw: Redis 原始消息 dict
        """
        if self._dispatch_fn is None:
            return

        channel = raw.get('channel', b'')
        if isinstance(channel, bytes):
            channel = channel.decode('utf-8', errors='replace')

        data = raw.get('data', b'')
        if isinstance(data, bytes):
            try:
                data = json.loads(data.decode('utf-8'))
            except (json.JSONDecodeError, UnicodeDecodeError):
                data = data.decode('utf-8', errors='replace')
        elif isinstance(data, str):
            # decode_responses=True 时 Redis 返回 str，需尝试 JSON 反序列化
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, ValueError):
                pass  # 保持原始字符串

        try:
            await self._dispatch_fn(channel, data)
        except Exception as e:
            logger.error(
                f'❌ dispatch 异常 (channel={channel}): {e}',
                exc_info=True,
            )

    async def _safe_close_pubsub(self) -> None:
        """安全关闭 pubsub 对象"""
        if self._pubsub:
            try:
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None


__all__ = ['RedisPubSubBackend']
