"""
@consumer 装饰器

业务方用 `@consumer(topic, group_id, ...)` 声明消费点,启动时全路径 import 触发注册。
装饰器与门面分开,职责清晰。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from knowledge_common.utils.log_util import logger


# 业务消费函数签名
MessageHandler = Callable[[Any], Awaitable[None]]
# 业务幂等键生成函数(可选)
BusinessIdFn = Callable[[Any], Any]


@dataclass(frozen=True)
class ConsumerInfo:
    """
    已注册消费者的元信息

    字段:
    - consumer_id:全局唯一标识(默认用 `{module}.{func.__name__}`)
    - topic / group_id:Kafka 风格订阅
    - handler:业务 async def(msg) -> None
    - business_id_fn:可选,业务幂等键生成函数
    - on_error:异常处理策略(目前仅 'retry' / 'rethrow')
    - max_retries:消费侧最大重试次数
    """

    consumer_id: str
    topic: str
    group_id: str
    handler: MessageHandler
    business_id_fn: BusinessIdFn | None = None
    on_error: str = 'retry'
    max_retries: int = 3


def consumer(
    topic: str,
    group_id: str,
    *,
    id: str | None = None,
    business_id_fn: BusinessIdFn | None = None,
    on_error: str = 'retry',
    max_retries: int = 3,
) -> Callable[[MessageHandler], MessageHandler]:
    """
    消费者装饰器工厂

    用法:
        @consumer(topic='log:op', group_id='log_writer')
        async def handle(msg: Message) -> None:
            ...

    装饰器立即注册到 MessageStreamService._consumers 表(类级别共享),
    discover_and_start() 时为每个 consumer 拉起后台协程。

    :param topic: 订阅的 topic
    :param group_id: 消费组
    :param id: 消费者唯一 id(默认用 `{module}.{func.__name__}`)
    :param business_id_fn: 可选,业务幂等键生成函数 `func(msg) -> any`
    :param on_error: 异常处理策略,默认 'retry'(重试到 max_retries 后由后端兜底)
    :param max_retries: 消费侧最大重试次数
    :return: 装饰器
    """
    # 局部 import 避免循环:service.py 也会被装饰器反向引用
    from knowledge_common.message_stream.service import MessageStreamService

    def decorator(func: MessageHandler) -> MessageHandler:
        consumer_id = id or f'{func.__module__}.{func.__name__}'

        # 同一 (模块路径, 函数名) 只注册一次,重复装饰跳过
        if consumer_id in MessageStreamService._consumers:
            logger.debug(
                f'消费者 {consumer_id} 已注册,跳过重复装饰(可能由 reload 导致)'
            )
            return func

        info = ConsumerInfo(
            consumer_id=consumer_id,
            topic=topic,
            group_id=group_id,
            handler=func,
            business_id_fn=business_id_fn,
            on_error=on_error,
            max_retries=max_retries,
        )
        MessageStreamService._consumers[consumer_id] = info
        logger.debug(
            f'✅ 消费者已注册: id={consumer_id} topic={topic} group={group_id}'
        )
        return func

    return decorator


__all__ = ['consumer', 'ConsumerInfo', 'MessageHandler', 'BusinessIdFn']
