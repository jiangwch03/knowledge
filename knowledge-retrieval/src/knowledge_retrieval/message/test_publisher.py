"""
knowledge-retrieval 消息流测试发送类

提供发送 demo 消息的统一入口,供:
- 应用启动时(lifespan)调用一次,验证生产-消费链路;
- 单元测试 / 手工脚本调用,本地排查消息流问题。

注:本类全 @classmethod,无需也不可以实例化。
"""
from __future__ import annotations

import time

from knowledge_common.message_stream import MessageStreamError, MessageStreamService
from knowledge_common.utils.log_util import logger


class RetrievalMessageTestPublisher:
    """
    retrieval 端测试发送类(对应 consumer/test_consumer.py)

    topic: test:retrieval:demo
    """

    TOPIC = 'test:retrieval:demo'

    @classmethod
    async def send_demo(cls, payload: dict | None = None) -> str | None:
        """
        发送一条 demo 测试消息

        :param payload: 消息内容,默认带时间戳的演示数据
        :return: 消息 ID(发送失败返回 None,不阻塞调用方)
        """
        # 消息内容
        value = payload or {
            'from': 'knowledge-retrieval',
            'scene': 'startup-demo',
            'ts': int(time.time() * 1000),
        }
        try:
            # 发送消息
            msg_id = await MessageStreamService.produce(
                topic=cls.TOPIC,
                value=value,
                key='retrieval-startup-demo',
            )
            logger.info(
                f'📤 [retrieval-test-publisher] 已发送测试消息: '
                f'topic={cls.TOPIC} id={msg_id} value={value}'
            )
            return msg_id
        except MessageStreamError as e:
            logger.warning(
                f'⚠️ [retrieval-test-publisher] 测试消息发送失败(忽略,不影响启动): {e}'
            )
            return None


__all__ = ['RetrievalMessageTestPublisher']
