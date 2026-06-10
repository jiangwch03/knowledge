"""
StreamBackend 抽象接口

定义消息流服务对底层中间件(Redis Stream / Kafka)的统一调用约定。
所有后端实现必须实现以下 6 个方法,藏住协议差异,保证切后端业务代码零修改。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from knowledge_common.message_stream.message import Message


class StreamBackend(ABC):
    """
    消息流后端抽象基类

    6 个核心方法:
    - publish:投递一条消息,返回消息 ID
    - consume:拉取一批消息(阻塞)
    - ack:确认消费(可批量)
    - create_group:创建消费组(幂等)
    - claim_idle:接管卡住消息(空闲超时)
    - shutdown:关闭后端连接
    """

    @abstractmethod
    async def publish(
        self,
        topic: str,
        value: object,
        key: str | None,
        headers: dict | None,
    ) -> str:
        """
        投递一条消息到 topic

        :param topic: 目标 topic
        :param value: 业务载荷(可序列化对象)
        :param key: 业务键(用于顺序保证 / 分区路由)
        :param headers: 头部元数据
        :return: 消息 ID(Stream xid 字符串 / Kafka offset 字符串化)
        :raises MessageStreamError: 投递失败
        """

    @abstractmethod
    async def consume(
        self,
        topic: str,
        group_id: str,
        consumer_id: str,
        block_ms: int,
        count: int,
    ) -> list['Message']:
        """
        阻塞拉取一批消息

        :param topic: 订阅的 topic
        :param group_id: 消费组(后端协议中性,后端各自映射)
        :param consumer_id: 当前消费者实例标识(同 group 内唯一)
        :param block_ms: 阻塞超时(毫秒)
        :param count: 最大拉取条数
        :return: 消息列表;空闲时返回空列表
        :raises MessageStreamError: 拉取失败
        """

    @abstractmethod
    async def ack(
        self,
        topic: str,
        group_id: str,
        *msg_offsets: str,
    ) -> int:
        """
        确认消费(批量)

        :param topic: 消息所在 topic
        :param group_id: 消费组
        :param msg_offsets: 待确认的消息 ID 列表
        :return: 实际确认条数
        :raises MessageStreamError: 确认失败
        """

    @abstractmethod
    async def create_group(
        self,
        topic: str,
        group_id: str,
    ) -> None:
        """
        创建消费组(BUSYGROUP 等已存在异常应被吞掉,保证幂等)

        :param topic: 目标 topic
        :param group_id: 消费组名
        :raises MessageStreamError: 创建失败(非幂等错误)
        """

    @abstractmethod
    async def claim_idle(
        self,
        topic: str,
        group_id: str,
        consumer_id: str,
        min_idle_ms: int,
    ) -> list['Message']:
        """
        接管空闲超时的卡住消息(用于 PEL 兜底)

        :param topic: 目标 topic
        :param group_id: 消费组
        :param consumer_id: 当前消费者实例标识
        :param min_idle_ms: 消息空闲超过该毫秒数才被接管
        :return: 被接管的消息列表
        :raises MessageStreamError: 接管失败
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """
        关闭后端连接(框架级 shutdown 时调用)
        """


__all__ = ['StreamBackend']
