"""
消息流后端工厂

按 ``MessageStreamSettings.message_stream_backend`` 字段创建对应后端实例。
业务方在 lifespan 中只需调 ``create_backend(settings, redis=app.state.redis)``,
切换后端只改 .env 即可,业务代码零修改。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from redis import asyncio as aioredis

from knowledge_common.message_stream.backends.base import StreamBackend
from knowledge_common.message_stream.exceptions import MessageStreamError

if TYPE_CHECKING:
    from knowledge_common.config.env import MessageStreamSettings


def create_backend(
    settings: 'MessageStreamSettings',
    *,
    redis: aioredis.Redis | None = None,
) -> StreamBackend:
    """
    根据 ``settings.message_stream_backend`` 字段创建后端实现

    :param settings: 消息流配置(读 .env)
    :param redis: Redis 后端必传,Kafka 后端忽略
    :return: 后端实例
    :raises MessageStreamError: 未知后端类型 / Redis 后端缺 redis 客户端
    """
    backend = settings.message_stream_backend

    if backend == 'redis':
        if redis is None:
            raise MessageStreamError(
                'Redis 后端需要注入 redis 客户端(由 lifespan 传入 app.state.redis)',
            )
        from knowledge_common.message_stream.backends.redis_stream import RedisStreamBackend
        return RedisStreamBackend(
            redis,
            maxlen=settings.message_stream_redis_maxlen,
        )

    if backend == 'kafka':
        from knowledge_common.message_stream.backends.kafka_stream import KafkaStreamBackend
        return KafkaStreamBackend(
            bootstrap_servers=settings.message_stream_kafka_bootstrap_servers,
            client_id=settings.message_stream_kafka_client_id,
            security_protocol=settings.message_stream_kafka_security_protocol,
            sasl_mechanism=settings.message_stream_kafka_sasl_mechanism or None,
            sasl_username=settings.message_stream_kafka_sasl_username or None,
            sasl_password=settings.message_stream_kafka_sasl_password or None,
            acks=settings.message_stream_kafka_acks,
            linger_ms=settings.message_stream_kafka_linger_ms,
            request_timeout_ms=settings.message_stream_kafka_request_timeout_ms,
            session_timeout_ms=settings.message_stream_kafka_session_timeout_ms,
            heartbeat_interval_ms=settings.message_stream_kafka_heartbeat_interval_ms,
            auto_offset_reset=settings.message_stream_kafka_auto_offset_reset,
            create_topic_partitions=settings.message_stream_kafka_create_topic_partitions,
            create_topic_replication_factor=settings.message_stream_kafka_create_topic_replication_factor,
        )

    raise MessageStreamError(f'未知消息流后端类型: {backend}')


__all__ = ['create_backend']
