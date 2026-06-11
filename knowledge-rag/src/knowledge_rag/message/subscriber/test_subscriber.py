"""
knowledge-rag 广播测试订阅者

订阅 channel=`test:rag:broadcast` 的消息，打印接收内容，验证广播端到端链路。
- channel: test:rag:broadcast

业务方可参考此文件，在同一包下新建其它订阅者文件即可被自动扫描注册。
"""
from __future__ import annotations

from knowledge_common.broadcast import BroadcastMessage, subscriber
from knowledge_common.utils.log_util import logger


@subscriber(channel='test:rag:broadcast')
async def handle_rag_test_broadcast(msg: BroadcastMessage) -> None:
    """
    rag 端广播测试订阅者

    :param msg: 广播消息对象(channel / payload / timestamp)
    :return: None
    """
    logger.info(
        f'📥 [rag-test-subscriber] 收到广播: '
        f'channel={msg.channel} payload={msg.payload}'
    )
