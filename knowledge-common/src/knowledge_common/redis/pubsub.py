"""
Redis Pub/Sub 工具类

提供发布/订阅的统一封装：
- 自动 JSON 序列化/反序列化
- 双层循环 + 异常自愈（永久存活）
- 支持精确订阅和模式订阅
- handler 支持同步/异步函数
- 任务生命周期管理

注意：所有方法都是 @classmethod，无需也不可以实例化。

典型用法：

    from redis import asyncio as aioredis
    from knowledge_common.redis import PubSubMessage, RedisPubSub

    redis: aioredis.Redis = ...

    # ============ 1. 发布 ============
    n = await RedisPubSub.publish(
        redis,
        'scheduler:global:sync',
        {'app_scope': 'knowledge-content', 'action': 'sync'},
    )

    # ============ 2. 订阅 ============
    async def on_message(msg: PubSubMessage):
        if msg.data.get('app_scope') != MY_APP:
            return
        await do_something(msg.data)

    task = await RedisPubSub.subscribe(
        redis,
        'scheduler:global:sync',
        on_message,
        task_name='my_subscriber',
    )

    # ============ 3. 取消订阅 ============
    await RedisPubSub.unsubscribe(task)
    # 应用关闭时一次性关闭全部
    # await RedisPubSub.shutdown()
"""
import asyncio
from typing import Any, Awaitable, Callable, Union

from redis import asyncio as aioredis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    TimeoutError as RedisTimeoutError,
)

from knowledge_common.common.context import RedisContext
from knowledge_common.redis.serialization import decode_message_data, encode_payload
from knowledge_common.utils.log_util import logger


# handler 接受 PubSubMessage，返回 None 或协程
MessageHandler = Callable[["PubSubMessage"], Union[Awaitable[None], None]]

# 发布载荷支持的类型
Payload = Union[dict, list, str, bytes, int, float, bool, None]


class PubSubMessage:
    """
    统一的消息结构

    屏蔽 Redis 原始消息中的 bytes/str 差异，自动 JSON 反序列化 payload
    """

    __slots__ = ("channel", "pattern", "data", "raw", "received_at")

    def __init__(self, channel: str, pattern: str | None, data: Any, raw: dict):
        self.channel = channel
        self.pattern = pattern
        self.data = data
        self.raw = raw
        self.received_at = asyncio.get_event_loop().time()

    def __repr__(self) -> str:
        return f"<PubSubMessage channel={self.channel} pattern={self.pattern} data={self.data}>"


class RedisPubSub:
    """
    Redis Pub/Sub 异步工具类

    所有方法均为类方法（与项目其他 util 风格保持一致）。
    Redis 客户端通过 knowledge_common.common.context.RedisContext 管理（server 生命周期级别），
    publish/subscribe 等接口无需重复传入 redis 参数。
    """

    # 已启动的订阅任务：{task_name: Task}
    _tasks: dict[str, asyncio.Task] = {}

    # 重连间隔（秒）
    _retry_interval: float = 5.0

    @classmethod
    def configure(cls, retry_interval: float = 5.0) -> None:
        """
        配置全局参数

        :param retry_interval: 订阅连接异常时的重连间隔（秒）
        :return: None
        """
        cls._retry_interval = retry_interval

    @classmethod
    def _get_redis(cls, redis: aioredis.Redis | None = None) -> aioredis.Redis:
        """
        获取可用的 redis 客户端（优先使用显式传入，否则使用 RedisContext 注入的）

        :param redis: 显式传入的 redis（可选）
        :return: aioredis 客户端
        :raises RuntimeError: 未初始化且未传入
        """
        if redis is not None:
            return redis
        return RedisContext.get_redis()

    # ==================== 发布 ====================

    @classmethod
    async def publish(cls, channel: str, payload: Payload, redis: aioredis.Redis | None = None) -> int:
        """
        发布消息（自动 JSON 序列化）

        :param channel: 频道名
        :param payload: 消息载荷，dict/list 会被自动 JSON 序列化
        :param redis: aioredis 客户端（可选，默认使用 init() 注入的）
        :return: 接收者数量
        """
        target_redis = cls._get_redis(redis)
        message = encode_payload(payload)
        n = await target_redis.publish(channel, message)
        logger.info(f'📢 发布到 [{channel}]: 接收者={n}')
        return n

    @classmethod
    def publish_sync(cls, channel: str, payload: Payload, redis=None) -> int:
        """
        同步发布消息

        :param channel: 频道名
        :param payload: 消息载荷
        :param redis: redis 客户端（非异步，可选，默认使用 init() 注入的）
        :return: 接收者数量
        """
        target_redis = cls._get_redis(redis)
        message = encode_payload(payload)
        n = target_redis.publish(channel, message)
        logger.info(f'📢 同步发布到 [{channel}]: 接收者={n}')
        return n

    # ==================== 订阅 ====================

    @classmethod
    async def subscribe(
        cls,
        channel: str,
        handler: MessageHandler,
        *,
        redis: aioredis.Redis | None = None,
        task_name: str | None = None,
    ) -> asyncio.Task:
        """
        精确订阅频道（启动后台监听任务）

        :param channel: 频道名
        :param handler: 消息处理函数，签名 `(msg: PubSubMessage) -> None | Awaitable[None]`
        :param redis: aioredis 客户端（可选，默认使用 init() 注入的）
        :param task_name: 任务名（用于去重和管理，默认 `pubsub:{channel}`）
        :return: 后台 asyncio.Task，调用 cancel() 即可取消订阅
        """
        target_redis = cls._get_redis(redis)
        return await cls._subscribe_internal(
            redis=target_redis,
            target=channel,
            handler=handler,
            pattern=False,
            task_name=task_name,
        )

    @classmethod
    async def subscribe_pattern(
        cls,
        pattern: str,
        handler: MessageHandler,
        *,
        redis: aioredis.Redis | None = None,
        task_name: str | None = None,
    ) -> asyncio.Task:
        """
        模式订阅（如 'news.*' 匹配 news.tech、news.sport）

        :param pattern: 模式字符串
        :param handler: 消息处理函数
        :param redis: aioredis 客户端（可选，默认使用 init() 注入的）
        :param task_name: 任务名
        :return: 后台 asyncio.Task
        """
        target_redis = cls._get_redis(redis)
        return await cls._subscribe_internal(
            redis=target_redis,
            target=pattern,
            handler=handler,
            pattern=True,
            task_name=task_name,
        )

    @classmethod
    async def _subscribe_internal(
        cls,
        redis: aioredis.Redis,
        target: str,
        handler: MessageHandler,
        pattern: bool,
        task_name: str | None,
    ) -> asyncio.Task:
        """订阅内部实现：去重 + 创建任务"""
        name = task_name or f'pubsub:{target}'

        # 防止重复订阅
        existing = cls._tasks.get(name)
        if existing and not existing.done():
            logger.warning(f'⚠️ 订阅任务 {name} 已在运行中，返回已有任务')
            return existing

        task = asyncio.create_task(
            cls._listen_loop(redis, target, handler, pattern, name)
        )
        cls._tasks[name] = task
        return task

    @classmethod
    async def _listen_loop(
        cls,
        redis: aioredis.Redis,
        target: str,
        handler: MessageHandler,
        pattern: bool,
        task_name: str,
    ) -> None:
        """
        双层循环实现：
        - 外层 while True：异常时整体重连
        - 内层 async for pubsub.listen()：阻塞读取维持 TCP 连接
        """
        method = 'psubscribe' if pattern else 'subscribe'
        target_type = 'pmessage' if pattern else 'message'

        while True:  # 外层：异常时整体重连
            pubsub = redis.pubsub()
            try:
                await getattr(pubsub, method)(target)
                logger.info(f'✅ 订阅成功: {target} (task={task_name})')

                async for raw_message in pubsub.listen():  # 内层：阻塞读取
                    if raw_message.get('type') != target_type:
                        continue
                    try:
                        msg = cls._parse_message(raw_message)
                        result = handler(msg)
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as e:
                        # handler 异常被吞掉，不影响订阅循环
                        logger.error(
                            f'❌ handler 处理消息异常 (channel={target}): {e}',
                            exc_info=True,
                        )
            except asyncio.CancelledError:
                # 主动取消（应用关闭）
                try:
                    await pubsub.unsubscribe(target)
                except Exception:
                    pass
                await pubsub.close()
                logger.info(f'🛑 订阅已取消: {target}')
                raise
            except (RedisConnectionError, RedisTimeoutError) as e:
                logger.warning(
                    f'⚠️ 订阅连接异常 ({target}): {e}，'
                    f'{cls._retry_interval} 秒后重试'
                )
                await pubsub.close()
                await asyncio.sleep(cls._retry_interval)
            except Exception as e:
                logger.error(
                    f'❌ 订阅异常 ({target}): {e}，'
                    f'{cls._retry_interval} 秒后重试',
                    exc_info=True,
                )
                await pubsub.close()
                await asyncio.sleep(cls._retry_interval)
            finally:
                try:
                    await pubsub.close()
                except Exception:
                    pass

    # ==================== 生命周期 ====================

    @classmethod
    async def unsubscribe(cls, task: asyncio.Task | str) -> None:
        """
        取消单个订阅

        :param task: asyncio.Task 或任务名
        :return: None
        """
        if isinstance(task, str):
            task = cls._tasks.pop(task, None)
        else:
            # 找到并移除同名的 task 引用
            for name, t in list(cls._tasks.items()):
                if t is task:
                    cls._tasks.pop(name, None)
                    break
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    @classmethod
    async def shutdown(cls) -> None:
        """
        关闭所有订阅任务（应用退出时调用）

        :return: None
        """
        if not cls._tasks:
            return
        tasks = list(cls._tasks.values())
        cls._tasks.clear()
        for t in tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        logger.info('🛑 所有 Pub/Sub 订阅已关闭')

    # ==================== 内部工具 ====================

    @staticmethod
    def _parse_message(raw: dict) -> PubSubMessage:
        """
        解析 Redis 原始消息

        - channel/pattern 统一为 str（处理 bytes）
        - data 使用公共 decode_message_data 解码
        """
        channel = raw.get('channel', '')
        if isinstance(channel, bytes):
            channel = channel.decode('utf-8', errors='replace')

        pattern = raw.get('pattern')
        if isinstance(pattern, bytes):
            pattern = pattern.decode('utf-8', errors='replace')

        data = decode_message_data(raw.get('data'))

        return PubSubMessage(
            channel=channel,
            pattern=pattern,
            data=data,
            raw=raw,
        )
