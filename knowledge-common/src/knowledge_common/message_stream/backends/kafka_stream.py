"""
Kafka 消息流后端实现(confluent-kafka-python 工业级客户端)

基于 ``confluent_kafka.aio.AIOProducer`` / ``AIOConsumer`` 实现 StreamBackend 抽象接口
的 6 个方法,藏住 Kafka 与 Redis Stream 的协议差异。
``AdminClient`` 是同步 API,用 ``asyncio.to_thread`` 包装避免阻塞事件循环。

字段映射约定:
- 业务 value  → bytes(json / str 直传)
- 业务 key    → bytes(utf-8)
- 业务 headers → list[tuple[str, bytes]]
- Message.offset = "<partition>:<offset>"(字符串化)
- Message.partition = Kafka partition(int)
- create_group 退化为「ensure topic exists」(Kafka 的 consumer group 是 lazy 自动 join)
- claim_idle 退化为「seek to committed 重读」(Kafka 无 PEL 概念)

依赖:confluent-kafka>=2.5.0(aio 模块自 2.5 起稳定)
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from confluent_kafka import KafkaError, KafkaException, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka.aio import AIOConsumer, AIOProducer
from pydantic import BaseModel

from knowledge_common.message_stream.backends.base import StreamBackend
from knowledge_common.message_stream.exceptions import MessageStreamError
from knowledge_common.message_stream.message import Message
from knowledge_common.utils.log_util import logger


# ==================== 字段编解码 ====================


def _encode_value(value: Any) -> bytes:
    """业务 value → Kafka 消息体 bytes"""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode('utf-8')
    if isinstance(value, BaseModel):
        return json.dumps(value.model_dump(), ensure_ascii=False, default=str).encode('utf-8')
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str).encode('utf-8')
    return str(value).encode('utf-8')


def _decode_value(raw: bytes | None) -> Any:
    """Kafka 消息体 bytes → 业务 value"""
    if raw is None:
        return None
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return raw
    if text and text[0] in '{[':
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return text
    return text


def _encode_headers(headers: dict | None) -> list[tuple[str, bytes]]:
    """业务 headers dict → Kafka headers 列表"""
    if not headers:
        return []
    out: list[tuple[str, bytes]] = []
    for k, v in headers.items():
        if isinstance(v, bytes):
            out.append((str(k), v))
        elif isinstance(v, str):
            out.append((str(k), v.encode('utf-8')))
        else:
            out.append((str(k), json.dumps(v, ensure_ascii=False, default=str).encode('utf-8')))
    return out


def _decode_headers(raw) -> dict[str, Any]:
    """Kafka headers 列表 → 业务 dict"""
    if not raw:
        return {}
    out: dict[str, Any] = {}
    for k, v in raw:
        try:
            text = v.decode('utf-8') if isinstance(v, (bytes, bytearray)) else str(v)
            if text and text[0] in '{[':
                out[k] = json.loads(text)
            else:
                out[k] = text
        except Exception:
            out[k] = v
    return out


# ==================== 后端实现 ====================


class KafkaStreamBackend(StreamBackend):
    """
    Kafka 消息流后端实现(基于 confluent-kafka-python 工业级客户端 + aio 异步包装)

    内部按需懒加载:
    - producer: 首次 publish 时创建(AIOProducer,自带 ThreadPoolExecutor)
    - admin:    首次 create_group 时创建(同步 AdminClient,操作走 to_thread)
    - consumer: 首次 consume / claim_idle 时按 (topic, group_id, consumer_id) 缓存

    生命周期:
    - shutdown() 统一 close 所有 producer / consumer
    """

    def __init__(
        self,
        *,
        bootstrap_servers: str = 'localhost:9092',
        client_id: str = 'knowledge',
        security_protocol: str = 'PLAINTEXT',
        sasl_mechanism: str | None = None,
        sasl_username: str | None = None,
        sasl_password: str | None = None,
        acks: str = 'all',
        linger_ms: int = 5,
        request_timeout_ms: int = 30000,
        session_timeout_ms: int = 10000,
        heartbeat_interval_ms: int = 3000,
        auto_offset_reset: str = 'earliest',
        create_topic_partitions: int = 1,
        create_topic_replication_factor: int = 1,
        max_workers: int = 5,
    ) -> None:
        # 通用客户端参数
        self._bootstrap_servers = bootstrap_servers
        self._client_id = client_id
        self._security_protocol = security_protocol
        self._sasl_mechanism = sasl_mechanism
        self._sasl_username = sasl_username
        self._sasl_password = sasl_password
        self._request_timeout_ms = request_timeout_ms
        # producer 专属
        self._acks = acks
        self._linger_ms = linger_ms
        # consumer 专属
        self._session_timeout_ms = session_timeout_ms
        self._heartbeat_interval_ms = heartbeat_interval_ms
        self._auto_offset_reset = auto_offset_reset
        # admin 专属
        self._create_topic_partitions = create_topic_partitions
        self._create_topic_replication_factor = create_topic_replication_factor
        # aio 线程池
        self._max_workers = max_workers

        # 懒加载资源
        self._producer: AIOProducer | None = None
        self._producer_lock = asyncio.Lock()
        self._admin: AdminClient | None = None
        self._admin_lock = asyncio.Lock()
        self._consumers: dict[str, AIOConsumer] = {}
        self._consumers_lock = asyncio.Lock()

    # ---------- librdkafka config 构造 ----------

    def _base_config(self) -> dict:
        """producer / consumer / admin 共用的鉴权 + 连接参数"""
        cfg: dict = {
            'bootstrap.servers': self._bootstrap_servers,
            'security.protocol': self._security_protocol,
        }
        if self._sasl_mechanism:
            cfg['sasl.mechanism'] = self._sasl_mechanism
            cfg['sasl.username'] = self._sasl_username or ''
            cfg['sasl.password'] = self._sasl_password or ''
        return cfg

    def _producer_config(self) -> dict:
        cfg = self._base_config()
        cfg.update({
            'client.id': self._client_id,
            'acks': self._acks,
            'linger.ms': self._linger_ms,
            'request.timeout.ms': self._request_timeout_ms,
        })
        return cfg

    def _consumer_config(self, group_id: str, consumer_id: str) -> dict:
        cfg = self._base_config()
        cfg.update({
            'group.id': group_id,
            'client.id': consumer_id,
            'auto.offset.reset': self._auto_offset_reset,
            'enable.auto.commit': False,
            'session.timeout.ms': self._session_timeout_ms,
            'heartbeat.interval.ms': self._heartbeat_interval_ms,
        })
        return cfg

    def _admin_config(self) -> dict:
        cfg = self._base_config()
        cfg['client.id'] = f'{self._client_id}-admin'
        return cfg

    # ---------- 客户端工厂 ----------

    async def _get_producer(self) -> AIOProducer:
        if self._producer is not None:
            return self._producer
        async with self._producer_lock:
            if self._producer is None:
                p = AIOProducer(self._producer_config(), max_workers=self._max_workers)
                # AIOProducer 在 __init__ 时启动内部 ThreadPoolExecutor,无需显式 start
                self._producer = p
                logger.info(
                    f'✅ confluent-kafka AIOProducer 启动: bootstrap={self._bootstrap_servers}',
                )
        return self._producer

    async def _get_admin(self) -> AdminClient:
        if self._admin is not None:
            return self._admin
        async with self._admin_lock:
            if self._admin is None:
                # AdminClient 构造是同步的,但内部只建立客户端句柄,不会阻塞
                self._admin = AdminClient(self._admin_config())
                logger.info(
                    f'✅ confluent-kafka AdminClient 启动: bootstrap={self._bootstrap_servers}',
                )
        return self._admin

    async def _get_consumer(
        self,
        topic: str,
        group_id: str,
        consumer_id: str,
    ) -> AIOConsumer:
        key = f'{topic}::{group_id}::{consumer_id}'
        if key in self._consumers:
            return self._consumers[key]
        async with self._consumers_lock:
            if key not in self._consumers:
                c = AIOConsumer(
                    self._consumer_config(group_id, consumer_id),
                    max_workers=self._max_workers,
                )
                # subscribe 触发实际的 rebalance / 拉取启动
                await c.subscribe([topic])
                self._consumers[key] = c
                logger.info(
                    f'✅ confluent-kafka AIOConsumer 启动: topic={topic} group={group_id} consumer={consumer_id}',
                )
        return self._consumers[key]

    # ---------- 字段解析 ----------

    @staticmethod
    def _parse_message(msg) -> Message:
        ts_type, ts_value = msg.timestamp()
        timestamp = ts_value if ts_type else 0
        return Message(
            topic=msg.topic(),
            key=msg.key().decode('utf-8', errors='replace') if msg.key() else None,
            value=_decode_value(msg.value()),
            headers=_decode_headers(msg.headers()),
            timestamp=timestamp,
            offset=f'{msg.partition()}:{msg.offset()}',
            partition=msg.partition(),
        )

    # ---------- StreamBackend 6 个方法 ----------

    async def publish(
        self,
        topic: str,
        value: Any,
        key: str | None,
        headers: dict | None,
    ) -> str:
        try:
            producer = await self._get_producer()
            value_bytes = _encode_value(value)
            key_bytes = key.encode('utf-8') if isinstance(key, str) else key
            headers_list = _encode_headers(headers)
            # AIOProducer.produce 是 awaitable,返回 asyncio.Future
            # await future 得到交付结果 Message(由回调包装)
            future = await producer.produce(
                topic=topic,
                value=value_bytes,
                key=key_bytes,
                headers=headers_list,
            )
            delivered = await future
            return f'{delivered.partition()}:{delivered.offset()}'
        except KafkaException as e:
            raise MessageStreamError(
                f'Kafka 协议错误,push 失败: {e}', topic=topic, cause=e,
            ) from e
        except BufferError as e:
            raise MessageStreamError(
                f'Kafka 本地队列已满,push 失败: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'push 失败: {e}', topic=topic, cause=e,
            ) from e

    async def consume(
        self,
        topic: str,
        group_id: str,
        consumer_id: str,
        block_ms: int,
        count: int,
    ) -> list[Message]:
        try:
            consumer = await self._get_consumer(topic, group_id, consumer_id)
        except KafkaException as e:
            raise MessageStreamError(
                f'Kafka 协议错误,consume 失败(初始化): {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'consume 失败(初始化): {e}', topic=topic, cause=e,
            ) from e

        timeout_sec = max(0.1, block_ms / 1000.0)
        messages: list[Message] = []
        for _ in range(count):
            try:
                msg = await consumer.poll(timeout_sec)
            except KafkaException as e:
                raise MessageStreamError(
                    f'Kafka 协议错误,poll 失败: {e}', topic=topic, cause=e,
                ) from e
            except Exception as e:
                raise MessageStreamError(
                    f'poll 失败: {e}', topic=topic, cause=e,
                ) from e
            if msg is None:
                break
            err = msg.error()
            if err is not None:
                # _PARTITION_EOF 不视为错误(单条 poll 时常遇到)
                if err.code() == KafkaError._PARTITION_EOF:
                    continue
                raise MessageStreamError(
                    f'Kafka 消息错误: {err}', topic=topic, cause=err,
                )
            messages.append(self._parse_message(msg))
        return messages

    async def ack(
        self,
        topic: str,
        group_id: str,
        *msg_offsets: str,
    ) -> int:
        """
        confluent-kafka commit 协议:
        - offsets 是 list[TopicPartition],offset 字段是 int(下一条要消费的位置)
        - asynchronous=False 时同步等待 broker 确认
        """
        if not msg_offsets:
            return 0
        try:
            committed = 0
            for key, consumer in list(self._consumers.items()):
                if not key.startswith(f'{topic}::{group_id}::'):
                    continue
                tps_to_commit: list[TopicPartition] = []
                for offset_str in msg_offsets:
                    try:
                        p_str, o_str = offset_str.split(':', 1)
                        partition = int(p_str)
                        offset = int(o_str) + 1  # commit next offset(已处理 + 1)
                    except (ValueError, IndexError):
                        continue
                    tps_to_commit.append(TopicPartition(topic, partition, offset))
                if tps_to_commit:
                    await consumer.commit(
                        offsets=tps_to_commit,
                        asynchronous=False,
                    )
                    committed += len(tps_to_commit)
            return committed
        except KafkaException as e:
            raise MessageStreamError(
                f'Kafka 协议错误,ack 失败: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'ack 失败: {e}', topic=topic, cause=e,
            ) from e

    async def create_group(self, topic: str, group_id: str) -> None:
        """
        Kafka 的 consumer group 是 lazy 自动 join,这里只确保 topic 存在
        """
        try:
            admin = await self._get_admin()
            new_topic = NewTopic(
                topic,
                num_partitions=self._create_topic_partitions,
                replication_factor=self._create_topic_replication_factor,
            )
            # AdminClient.create_topics 同步,内部用 to_thread 包装
            futures = await asyncio.to_thread(admin.create_topics, [new_topic])
            for topic_name, future in futures.items():
                try:
                    result = await asyncio.to_thread(future.result, 30.0)
                    # result 是 list[TopicPartition],含 error 字段
                    if isinstance(result, list):
                        for tp in result:
                            if tp.error is not None:
                                if tp.error.code() == KafkaError.TOPIC_ALREADY_EXISTS:
                                    logger.debug(f'Kafka topic 已存在(幂等): {topic_name}')
                                else:
                                    raise MessageStreamError(
                                        f'create_topic 失败: {tp.error}', topic=topic,
                                    )
                        else:
                            logger.info(f'✅ Kafka topic 创建成功: {topic_name}')
                except MessageStreamError:
                    raise
                except Exception as e:
                    # 兼容不同 confluent-kafka 版本的异常类型
                    err_str = str(e).lower()
                    if 'already exists' in err_str or 'topic_already_exists' in err_str:
                        logger.debug(f'Kafka topic 已存在(幂等): {topic_name}')
                    else:
                        raise MessageStreamError(
                            f'create_topic 失败: {e}', topic=topic, cause=e,
                        ) from e
        except MessageStreamError:
            raise
        except KafkaException as e:
            raise MessageStreamError(
                f'Kafka 协议错误,create_group 失败: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'create_group 失败: {e}', topic=topic, cause=e,
            ) from e

    async def claim_idle(
        self,
        topic: str,
        group_id: str,
        consumer_id: str,
        min_idle_ms: int,
    ) -> list[Message]:
        """
        Kafka 无 PEL 概念,退化为「seek to committed 重读未提交消息」
        """
        try:
            consumer = await self._get_consumer(topic, group_id, consumer_id)
            # 取已分配 partitions
            assignment = await asyncio.to_thread(consumer.assignment)
            if not assignment:
                return []
            # 查每个 partition 的已提交 offset
            committed_list = await asyncio.to_thread(
                consumer.committed, list(assignment), 5.0,
            )
            if not committed_list:
                return []
            # seek 到已提交位置
            for tp in committed_list:
                # tp.offset < 0 表示 OFFSET_INVALID,跳过
                if tp.offset >= 0:
                    await asyncio.to_thread(consumer.seek, tp)
            # 拉一批
            messages: list[Message] = []
            for _ in range(100):
                try:
                    msg = await consumer.poll(1.0)
                except Exception:
                    break
                if msg is None:
                    break
                err = msg.error()
                if err is None:
                    messages.append(self._parse_message(msg))
            return messages
        except KafkaException as e:
            raise MessageStreamError(
                f'Kafka 协议错误,claim_idle 失败: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'claim_idle 失败: {e}', topic=topic, cause=e,
            ) from e

    async def shutdown(self) -> None:
        # 关闭所有 consumer
        for _key, consumer in list(self._consumers.items()):
            try:
                await consumer.close()
            except Exception as e:
                logger.warning(f'⚠️ consumer close 异常(忽略): {e}')
        self._consumers.clear()
        # 关闭 producer
        if self._producer is not None:
            try:
                await self._producer.close()
            except Exception as e:
                logger.warning(f'⚠️ producer close 异常(忽略): {e}')
            self._producer = None
        # AdminClient 是同步 API,无 close 方法
        self._admin = None
        logger.info('🛑 KafkaStreamBackend(confluent-kafka) 已关闭')


__all__ = ['KafkaStreamBackend']
