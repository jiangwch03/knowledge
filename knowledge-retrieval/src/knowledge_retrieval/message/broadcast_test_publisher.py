"""
knowledge-retrieval 广播测试发送类

提供发送 demo 广播的统一入口，供:
- 应用启动时(lifespan)调用一次，验证广播端到端链路;
- 单元测试 / 手工脚本调用，本地排查广播问题。

注: 本类全 @classmethod，无需也不可以实例化。
"""
from __future__ import annotations

import time

from knowledge_common.broadcast import BroadcastError, BroadcastService
from knowledge_common.utils.log_util import logger


class RetrievalBroadcastTestPublisher:
    """
    retrieval 端广播测试发送类(对应 subscriber/test_subscriber.py)

    channel: test:retrieval:broadcast
    """

    CHANNEL = 'test:retrieval:broadcast'

    @classmethod
    async def send_demo(cls, payload: dict | None = None) -> int | None:
        """
        发送一条 demo 广播消息

        :param payload: 消息内容，默认带时间戳的演示数据
        :return: 接收者数量(发送失败返回 None，不阻塞调用方)
        """
        value = payload or {
            'from': 'knowledge-retrieval',
            'scene': 'startup-broadcast-demo',
            'ts': int(time.time() * 1000),
        }
        try:
            receivers = await BroadcastService.publish(
                channel=cls.CHANNEL,
                payload=value,
            )
            logger.info(
                f'📤 [retrieval-broadcast-test] 已发送测试广播: '
                f'channel={cls.CHANNEL} receivers={receivers} payload={value}'
            )
            return receivers
        except BroadcastError as e:
            logger.warning(
                f'⚠️ [retrieval-broadcast-test] 测试广播发送失败(忽略,不影响启动): {e}'
            )
            return None


__all__ = ['RetrievalBroadcastTestPublisher']
