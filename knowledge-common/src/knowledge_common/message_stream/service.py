"""
MessageStreamService 门面

全 @classmethod,提供:
- init(backend):注入后端
- register_consumer_paths(paths):业务方声明消费者所在包路径
- discover_and_start():扫描 + 拉起后台消费协程
- produce(...):推送消息(带重试,失败抛 MessageStreamError)
- shutdown():优雅关闭
- reset():单元测试用

所有方法都是 @classmethod,无需也不可以实例化。
"""
from __future__ import annotations

import asyncio
import importlib
import pkgutil
from typing import Any

from knowledge_common.message_stream.backends.base import StreamBackend
from knowledge_common.message_stream.consumer import ConsumerInfo
from knowledge_common.message_stream.exceptions import MessageStreamError
from knowledge_common.message_stream.message import Message
from knowledge_common.utils.log_util import logger


# 消费拉取参数(可由 .env 后续覆盖,目前先硬编码)
_DEFAULT_BLOCK_MS = 2000
_DEFAULT_BATCH_SIZE = 100
_CLAIM_IDLE_MS = 60_000
_CLAIM_INTERVAL_MS = 5_000


class MessageStreamService:
    """
    消息流服务门面

    业务方:
        from knowledge_common.message_stream import consumer, MessageStreamService

        @consumer(topic='log:op', group_id='log_writer')
        async def handle(msg): ...

        # 推送
        await MessageStreamService.produce(topic='log:op', value={'k': 'v'}, key='doc_1')
    """

    # 后端实现(由 init 注入)
    _backend: StreamBackend | None = None

    # 已注册消费者(由 @consumer 装饰器写入)
    _consumers: dict[str, ConsumerInfo] = {}

    # 后台消费协程:{consumer_id: Task}
    _tasks: dict[str, asyncio.Task] = {}

    # 业务方声明的扫描路径
    _scan_paths: list[str] = ['knowledge_common.message.consumer']

    # 后台 idle 接管协程:{consumer_id: Task}
    _claim_tasks: dict[str, asyncio.Task] = {}

    # ==================== 生命周期 ====================

    @classmethod
    def init(cls, backend: StreamBackend) -> None:
        """
        注入后端实现(应用启动时调用一次)

        :param backend: 实现了 StreamBackend 6 个方法的对象
        """
        cls._backend = backend
        logger.info(f'✅ MessageStreamService 已初始化,backend={type(backend).__name__}')

    @classmethod
    def init_from_settings(
        cls,
        settings,
        *,
        redis=None,
    ) -> StreamBackend:
        """
        按 ``settings.message_stream_backend`` 注入后端(推荐使用)

        业务方在 lifespan 中调用:
            from knowledge_common.config.env import MessageStreamConfig
            MessageStreamService.init_from_settings(
                MessageStreamConfig, redis=app.state.redis,
            )

        切换后端只改 .env 即可(MESSAGE_STREAM_BACKEND=redis|kafka),
        业务代码零修改。

        :param settings: ``MessageStreamSettings`` 实例
        :param redis: Redis 后端必传,Kafka 后端可忽略
        :return: 创建的后端实例
        """
        # 局部 import 避免启动期循环
        from knowledge_common.message_stream.backends.factory import create_backend

        backend = create_backend(settings, redis=redis)
        cls.init(backend)
        return backend

    @classmethod
    def register_consumer_paths(cls, paths: list[str]) -> None:
        """
        注册业务方消费者所在包路径(discover_and_start 时按需 import 扫描)

        业务方在 lifespan 中调用:
            MessageStreamService.register_consumer_paths(['knowledge_admin.service'])

        多次调用累加(同进程 admin + rag 场景)。
        """
        added = False
        for p in paths:
            if p and p not in cls._scan_paths:
                cls._scan_paths.append(p)
                added = True
        if added:
            logger.info(f'📋 消费者扫描路径已注册: {cls._scan_paths}')

    @classmethod
    async def discover_and_start(cls) -> None:
        """
        扫描所有声明路径(import 触发装饰器注册),再为每个消费者拉起后台协程

        调用顺序:
            init(backend)
            register_consumer_paths([...])
            await discover_and_start()
        """
        if cls._backend is None:
            raise MessageStreamError(
                'MessageStreamService 未 init,调用 MessageStreamService.init(backend) 先注入后端',
            )

        if not cls._scan_paths:
            # 业务方忘记调用 register_consumer_paths,警告但不抛异常(开发模式友好)
            logger.warning(
                '⚠️ 未调用 register_consumer_paths 注册任何扫描路径,'
                '可能没有消费者需要启动。生产环境建议显式注册。',
            )
            return  # 没有扫描路径则不做任何事,早退(避免后续空循环)

        # 1) 扫描 + import,触发 @consumer 装饰器注册
        for path in list(cls._scan_paths):
            cls._import_subtree(path)

        if not cls._consumers:
            logger.warning('⚠️ 扫描完成,但未发现任何 @consumer 装饰的消费者')
            return

        # 2) 为每个 consumer 拉起后台消费协程
        for consumer_id, info in list(cls._consumers.items()):
            if consumer_id in cls._tasks and not cls._tasks[consumer_id].done():
                logger.debug(f'消费者 {consumer_id} 后台协程已在运行,跳过')
                continue
            # 先确保消费组存在(幂等)
            try:
                await cls._backend.create_group(info.topic, info.group_id)
            except MessageStreamError as e:
                logger.exception(
                    '❌ 消费组创建失败,跳过该消费者: id={} topic={} err={}',
                    consumer_id, info.topic, e,
                )
                continue

            task = asyncio.create_task(
                cls._consume_loop(info),
                name=f'msg-stream:consume:{consumer_id}',
            )
            cls._tasks[consumer_id] = task
            logger.info(
                f'🚀 消费者后台协程已启动: id={consumer_id} topic={info.topic} group={info.group_id}',
            )

            # 拉起 idle 接管协程(PEL 兜底)
            claim_task = asyncio.create_task(
                cls._claim_idle_loop(info),
                name=f'msg-stream:claim:{consumer_id}',
            )
            cls._claim_tasks[consumer_id] = claim_task

    @classmethod
    async def shutdown(cls) -> None:
        """
        优雅关闭:取消所有后台协程、调 backend.shutdown、清空状态

        在 FastAPI lifespan 退出阶段调用。
        """
        # 取消消费协程
        consume_tasks = list(cls._tasks.values())
        cls._tasks.clear()
        for t in consume_tasks:
            if not t.done():
                t.cancel()
        if consume_tasks:
            await asyncio.gather(*consume_tasks, return_exceptions=True)

        # 取消 idle 接管协程
        claim_tasks = list(cls._claim_tasks.values())
        cls._claim_tasks.clear()
        for t in claim_tasks:
            if not t.done():
                t.cancel()
        if claim_tasks:
            await asyncio.gather(*claim_tasks, return_exceptions=True)

        # 关闭后端
        if cls._backend is not None:
            try:
                await cls._backend.shutdown()
            except Exception as e:
                logger.opt(exception=True).warning('⚠️ backend.shutdown 异常(忽略): {}', e)

        logger.info('🛑 MessageStreamService 已关闭')

    @classmethod
    def reset(cls) -> None:
        """
        清空所有类变量(单元测试用)

        生产代码请勿调用。
        """
        cls._backend = None
        cls._consumers.clear()
        cls._tasks.clear()
        cls._claim_tasks.clear()
        cls._scan_paths.clear()

    # ==================== 推送 ====================

    @classmethod
    async def produce(
        cls,
        topic: str,
        value: Any,
        *,
        key: str | None = None,
        headers: dict | None = None,
        max_retries: int = 3,
        retry_interval: float = 0.5,
    ) -> str:
        """
        推送消息(带重试)

        :param topic: 目标 topic
        :param value: 业务载荷
        :param key: 业务键(顺序保证 / 分区路由)
        :param headers: 头部元数据
        :param max_retries: 最大重试次数(默认 3)
        :param retry_interval: 重试间隔(秒,默认 0.5)
        :return: 消息 ID
        :raises MessageStreamError: 重试用完仍未成功
        """
        if cls._backend is None:
            raise MessageStreamError('MessageStreamService 未 init', topic=topic)

        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                msg_id = await cls._backend.publish(topic, value, key, headers)
                if attempt > 1:
                    logger.info(
                        f'✅ push 成功(重试 {attempt - 1} 次后): topic={topic} id={msg_id}',
                    )
                return msg_id
            except MessageStreamError as e:
                last_exc = e
                if attempt < max_retries:
                    logger.opt(exception=True).warning(
                        '⚠️ push 失败(第 {}/{} 次): topic={} err={}, {}s 后重试',
                        attempt, max_retries, topic, e, retry_interval,
                    )
                    await asyncio.sleep(retry_interval)
                else:
                    logger.exception(
                        '❌ push 失败(已重试 {} 次): topic={} err={}',
                        max_retries, topic, e,
                    )
            except Exception as e:
                # 兜底:任何非 MessageStreamError 也包装为 MessageStreamError
                last_exc = e
                if attempt < max_retries:
                    logger.opt(exception=True).warning(
                        '⚠️ push 未知异常(第 {}/{} 次): topic={} err={!r}',
                        attempt, max_retries, topic, e,
                    )
                    await asyncio.sleep(retry_interval)

        raise MessageStreamError(
            f'push 失败,已重试 {max_retries} 次: {last_exc}',
            topic=topic,
            cause=last_exc,
        )

    # ==================== 内部:扫描与协程 ====================

    @classmethod
    def _import_subtree(cls, package_name: str) -> None:
        """
        反射 import 指定包及其子包(触发 @consumer 装饰器注册)

        复用 pkgutil.iter_modules 递归遍历。
        """
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.exception('❌ 扫描路径 import 失败: {} err={}', package_name, e)
            return

        for _finder, name, is_pkg in pkgutil.iter_modules(package.__path__):
            full_name = f'{package_name}.{name}'
            try:
                importlib.import_module(full_name)
            except ImportError as e:
                logger.exception('❌ 扫描子模块 import 失败: {} err={}', full_name, e)
                continue
            if is_pkg:
                cls._import_subtree(full_name)

    @classmethod
    async def _consume_loop(cls, info: ConsumerInfo) -> None:
        """
        单个消费者的后台消费循环(Worker 池模型)

        - 按 max_concurrency 控制并发度,同一批消息可并发处理
        - 每条消息独立处理、独立 ACK,单条失败不影响同批其他消息
        - 业务正常返回 → ack
        - 业务抛异常 → 不 ack,由后端协议兜底(PEL 接管 / Kafka 重平衡)
        """
        assert cls._backend is not None
        backend = cls._backend
        sem = asyncio.Semaphore(info.max_concurrency)

        async def _process_one(msg: Message) -> None:
            """
            单条消息处理(受 Semaphore 限流)

            - Semaphore 保证同时最多 max_concurrency 条消息在执行
            - 单条 handler 抛异常 → 捕获日志,不 ACK(由后端 claim 兜底)
            - 单条 handler 正常返回 → 自动 ACK
            - pre_ack 模式:handler 执行前先 ACK,消息移出 PEL
            """
            async with sem:
                try:
                    if info.pre_ack:
                        await backend.ack(
                            info.topic, info.group_id, msg.offset,
                        )
                    await info.handler(msg)
                    if not info.pre_ack:
                        await backend.ack(
                            info.topic, info.group_id, msg.offset,
                        )
                except Exception as e:
                    if info.pre_ack:
                        logger.error(
                            f'❌ 消费处理异常(已前置 ACK,需业务自行兜底): '
                            f'consumer={info.consumer_id} offset={msg.offset} '
                            f'err={e!r}',
                            exc_info=True,
                        )
                    else:
                        logger.error(
                            f'❌ 消费处理异常(不 ack,后端兜底): '
                            f'consumer={info.consumer_id} topic={info.topic} '
                            f'offset={msg.offset} err={e!r}',
                            exc_info=True,
                        )

        while True:
            try:
                while True:
                    messages = await backend.consume(
                        topic=info.topic,
                        group_id=info.group_id,
                        consumer_id=info.consumer_id,
                        block_ms=_DEFAULT_BLOCK_MS,
                        count=_DEFAULT_BATCH_SIZE,
                    )
                    if not messages:
                        continue  # 空闲,继续阻塞拉取

                    # 批次内消息并发处理(Worker 池)
                    # Semaphore 控制同时最多 max_concurrency 条,其余排队等待
                    tasks = [
                        asyncio.create_task(_process_one(msg))
                        for msg in messages
                    ]
                    # return_exceptions=True:单条 handler 异常不传播,gather 正常返回
                    await asyncio.gather(*tasks, return_exceptions=True)

            except asyncio.CancelledError:
                logger.info(
                    f'🛑 消费协程已取消: consumer={info.consumer_id} topic={info.topic}',
                )
                raise
            except MessageStreamError as e:
                logger.opt(exception=True).warning(
                    '⚠️ 消费异常,5s 后重试: consumer={} topic={} err={}',
                    info.consumer_id, info.topic, e,
                )
                await asyncio.sleep(5.0)
            except Exception as e:
                logger.exception(
                    '❌ 消费未知异常,5s 后重试: consumer={} err={!r}',
                    info.consumer_id, e,
                )
                await asyncio.sleep(5.0)

    @classmethod
    async def _claim_idle_loop(cls, info: ConsumerInfo) -> None:
        """
        idle 消息接管协程(PEL 兜底,Stream 专属)

        周期调用 backend.claim_idle,接管空闲超时的卡住消息。
        切到 Kafka 后端后,这个循环仍存在但 claim_idle 退化为"按未 commit 区间 seek 重读"。
        """
        assert cls._backend is not None
        backend = cls._backend
        consumer_id = f'{info.consumer_id}-claim'

        while True:
            try:
                claimed = await backend.claim_idle(
                    topic=info.topic,
                    group_id=info.group_id,
                    consumer_id=consumer_id,
                    min_idle_ms=_CLAIM_IDLE_MS,
                )
                for msg in claimed:
                    try:
                        await info.handler(msg)
                        await backend.ack(info.topic, info.group_id, msg.offset)
                    except Exception as e:
                        logger.exception(
                            '❌ idle 消息处理失败: consumer={} offset={} err={!r}',
                            info.consumer_id, msg.offset, e,
                        )
            except asyncio.CancelledError:
                logger.info(
                    f'🛑 idle 接管协程已取消: consumer={info.consumer_id}',
                )
                raise
            except MessageStreamError as e:
                logger.opt(exception=True).warning(
                    '⚠️ idle 接管异常: consumer={} err={}',
                    info.consumer_id, e,
                )
            except Exception as e:
                logger.exception(
                    '❌ idle 接管未知异常: consumer={} err={!r}',
                    info.consumer_id, e,
                )
            await asyncio.sleep(_CLAIM_INTERVAL_MS / 1000.0)


__all__ = ['MessageStreamService']
