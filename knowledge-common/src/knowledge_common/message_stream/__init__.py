"""
消息流服务

Kafka 风格的 Python 消息流门面(中间件无关,Redis Stream / Kafka 双后端可插拔)。

典型用法:
    from knowledge_common.message_stream import consumer, MessageStreamService
    from knowledge_common.message_stream.backends.factory import create_backend
    from knowledge_common.config.env import MessageStreamConfig
    from knowledge_common.common.context import RedisContext

    # 1. 业务方声明消费者
    @consumer(topic='log:op', group_id='log_writer')
    async def handle(msg): ...

    # 2. lifespan 注入(.env 改 MESSAGE_STREAM_BACKEND 即可切换 redis / kafka)
    MessageStreamService.init_from_settings(
        MessageStreamConfig, redis=app.state.redis,
    )
    MessageStreamService.register_consumer_paths(['knowledge_admin.message.consumer'])
    await MessageStreamService.discover_and_start()

    # 3. 业务推送
    await MessageStreamService.produce(topic='log:op', value={'k': 'v'}, key='doc_1')
"""
from knowledge_common.message_stream.consumer import ConsumerInfo, consumer
from knowledge_common.message_stream.exceptions import MessageStreamError
from knowledge_common.message_stream.message import Message
from knowledge_common.message_stream.service import MessageStreamService

__all__ = [
    'MessageStreamService',
    'consumer',
    'ConsumerInfo',
    'Message',
    'MessageStreamError',
]