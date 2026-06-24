"""
knowledge-content 测试消费者示例

订阅 topic=`test:rag:demo` 的消息,打印接收内容,验证消息流端到端链路。
- topic:   test:rag:demo
- group:   rag_test_demo

业务方可参考此文件,在同一包下新建其它消费者文件即可被自动扫描注册。
"""
from __future__ import annotations

from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.message_stream import Message, consumer
from knowledge_common.utils.log_util import logger


@consumer(topic='test:rag:demo', group_id = StreamTopicConfig.group_id)
async def handle_rag_test_demo(msg: Message) -> None:
    """
    rag 端测试消费者

    :param msg: 消息对象(topic / key / value / headers / offset)
    :return: None
    """
    logger.info(
        f'📥 [rag-test-consumer] 收到消息: '
        f'topic={msg.topic} key={msg.key} offset={msg.offset} value={msg.value}'
    )
