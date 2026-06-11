"""
消息广播服务

Redis Pub/Sub 广播抽象层，提供 @subscriber 装饰器 + BroadcastService 门面。
业务代码完全隔离 Redis 操作，后端可替换。

典型用法:
    from knowledge_common.broadcast import subscriber, BroadcastService, BroadcastMessage

    # 1. 业务方声明订阅者
    @subscriber(channel='scheduler:global:sync')
    async def on_sync(msg: BroadcastMessage) -> None: ...

    # 2. lifespan 注入
    BroadcastService.init(redis=app.state.redis)
    BroadcastService.register_subscriber_paths(['knowledge_common.message.subscriber'])
    await BroadcastService.discover_and_start()

    # 3. 业务发布
    await BroadcastService.publish('scheduler:global:sync', {'action': 'sync'})
"""
from knowledge_common.broadcast.exceptions import BroadcastError
from knowledge_common.broadcast.message import BroadcastMessage
from knowledge_common.broadcast.service import BroadcastService
from knowledge_common.broadcast.subscriber import SubscriberInfo, subscriber

__all__ = [
    'BroadcastService',
    'subscriber',
    'SubscriberInfo',
    'BroadcastMessage',
    'BroadcastError',
]
