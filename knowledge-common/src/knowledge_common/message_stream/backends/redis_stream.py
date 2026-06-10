"""
Redis Stream 后端实现

基于 redis.asyncio 封装 Stream 协议(XADD/XREADGROUP/XACK/XAUTOCLAIM),
实现 StreamBackend 抽象接口,藏住 Redis Stream 与 Kafka 的协议差异。

字段映射约定:
- 业务 value  → xadd fields['__value'] = json.dumps(value)
- 业务 key    → xadd fields['__key']   = key
- 业务 headers → xadd fields['__headers'] = json.dumps(headers)
- 业务以外不传:fields 全部以上面三个 magic key 表达
- 读取时:反序列化 __value / __headers 为 Python 对象,__key 还原为 key
- xid          → Message.offset
- 毫秒时间戳    → xadd 之后用 xrevrange 不可行,本实现从 message_id 解析(Redis Stream xid 含 ms timestamp)
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from redis import asyncio as aioredis
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
    ResponseError,
    TimeoutError as RedisTimeoutError,
)

from knowledge_common.message_stream.backends.base import StreamBackend
from knowledge_common.message_stream.exceptions import MessageStreamError
from knowledge_common.message_stream.message import Message
from knowledge_common.utils.log_util import logger

if TYPE_CHECKING:
    pass


# 业务字段在 Redis Stream fields 中的 key(用 __ 前缀避免和业务字段冲突)
_FIELD_VALUE = '__value'
_FIELD_KEY = '__key'
_FIELD_HEADERS = '__headers'


def _encode_field_value(value: Any) -> str:
    """业务 value 序列化为 str(写入 xadd fields)"""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)


def _decode_field_value(raw: str) -> Any:
    """业务 value 反序列化(读取 xreadgroup fields)"""
    # 启发式:JSON 字符串首字符为 { / [ 时才尝试解析,避免 str 误判
    if not raw:
        return None
    if raw[0] in '{[':
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw
    return raw


def _encode_field_headers(headers: dict | None) -> str:
    """headers 序列化为 JSON 字符串"""
    return json.dumps(headers or {}, ensure_ascii=False, default=str)


def _decode_field_headers(raw: str | None) -> dict:
    """headers 反序列化为 dict"""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {}


def _parse_stream_xid_timestamp(xid: str) -> int:
    """
    从 Redis Stream xid 解析毫秒时间戳

    Redis Stream xid 格式: "<ms>-<seq>",例 "1700000000000-0"
    """
    try:
        return int(xid.split('-', 1)[0])
    except (ValueError, IndexError):
        return 0


class RedisStreamBackend(StreamBackend):
    """
    Redis Stream 后端实现

    依赖 aioredis.Redis 客户端(由调用方注入;推荐从 RedisContext.get_redis() 获取)。
    """

    def __init__(
        self,
        redis: aioredis.Redis,
        *,
        maxlen: int = 100_000,
    ) -> None:
        """
        :param redis: aioredis 客户端
        :param maxlen: 近似裁剪上限(xadd MAXLEN ~ N),防止 stream 无限增长
        """
        self._redis = redis
        self._maxlen = maxlen

    # ==================== 字段装配 ====================

    def _build_fields(
        self,
        value: Any,
        key: str | None,
        headers: dict | None,
    ) -> dict[str, str]:
        """
        把 (value, key, headers) 装配为 Redis Stream fields

        Stream fields 必须是 str 类型,value 业务对象 JSON 序列化到 __value。
        """
        fields: dict[str, str] = {_FIELD_VALUE: _encode_field_value(value)}
        if key is not None:
            fields[_FIELD_KEY] = str(key)
        if headers:
            fields[_FIELD_HEADERS] = _encode_field_headers(headers)
        return fields

    def _parse_message(
        self,
        topic: str,
        xid: str,
        fields: dict[str, str],
    ) -> Message:
        """
        把 Redis Stream 单条消息 (xid, fields) 装配为 Message

        decode_responses=True 时,fields 已经是 dict[str, str]。
        """
        return Message(
            topic=topic,
            key=fields.get(_FIELD_KEY),
            value=_decode_field_value(fields.get(_FIELD_VALUE, '')),
            headers=_decode_field_headers(fields.get(_FIELD_HEADERS)),
            timestamp=_parse_stream_xid_timestamp(xid),
            offset=xid,
            partition=None,  # Redis Stream 无分区概念
        )

    # ==================== StreamBackend 6 个方法 ====================

    async def publish(
        self,
        topic: str,
        value: Any,
        key: str | None,
        headers: dict | None,
    ) -> str:
        try:
            fields = self._build_fields(value, key, headers)
            xid = await self._redis.xadd(
                name=topic,
                fields=fields,
                maxlen=self._maxlen,
                approximate=True,
            )
            return str(xid)
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise MessageStreamError(
                f'Redis 连接异常,push 失败: {e}', topic=topic, cause=e,
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
            response = await self._redis.xreadgroup(
                groupname=group_id,
                consumername=consumer_id,
                streams={topic: '>'},
                count=count,
                block=block_ms,
            )
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise MessageStreamError(
                f'Redis 连接异常,consume 失败: {e}', topic=topic, cause=e,
            ) from e
        except ResponseError as e:
            # NOGROUP 等协议错误:转 MessageStreamError 让上层重试
            raise MessageStreamError(
                f'consume 协议错误: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'consume 失败: {e}', topic=topic, cause=e,
            ) from e

        if not response:
            return []

        # response 形如:[[topic, [(xid, fields), ...]], ...]
        messages: list[Message] = []
        for stream_topic, entries in response:
            for xid, fields in entries:
                messages.append(self._parse_message(stream_topic, xid, fields))
        return messages

    async def ack(
        self,
        topic: str,
        group_id: str,
        *msg_offsets: str,
    ) -> int:
        if not msg_offsets:
            return 0
        try:
            # redis-py 接受 *ids 形式
            count = await self._redis.xack(topic, group_id, *msg_offsets)
            return int(count)
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise MessageStreamError(
                f'Redis 连接异常,ack 失败: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'ack 失败: {e}', topic=topic, cause=e,
            ) from e

    async def create_group(
        self,
        topic: str,
        group_id: str,
    ) -> None:
        try:
            # MKSTREAM:topic 不存在时自动创建
            await self._redis.xgroup_create(
                name=topic,
                groupname=group_id,
                id='$',
                mkstream=True,
            )
            logger.info(f'✅ 消费组创建成功: topic={topic} group={group_id}')
        except ResponseError as e:
            # BUSYGROUP:组已存在,幂等成功
            err_str = str(e)
            if 'BUSYGROUP' in err_str:
                logger.debug(f'消费组已存在(幂等): topic={topic} group={group_id}')
                return
            raise MessageStreamError(
                f'create_group 协议错误: {e}', topic=topic, cause=e,
            ) from e
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise MessageStreamError(
                f'Redis 连接异常,create_group 失败: {e}', topic=topic, cause=e,
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
        try:
            # xautoclaim 返回 [next_cursor, [(xid, fields), ...], deleted_ids]
            # min-idle-time 以毫秒为单位(redis-py 接受 int ms)
            response = await self._redis.xautoclaim(
                name=topic,
                groupname=group_id,
                consumername=consumer_id,
                min_idle_time=min_idle_ms,
                start_id='0-0',
                count=None,
            )
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise MessageStreamError(
                f'Redis 连接异常,claim_idle 失败: {e}', topic=topic, cause=e,
            ) from e
        except ResponseError as e:
            raise MessageStreamError(
                f'claim_idle 协议错误: {e}', topic=topic, cause=e,
            ) from e
        except Exception as e:
            raise MessageStreamError(
                f'claim_idle 失败: {e}', topic=topic, cause=e,
            ) from e

        if not response or len(response) < 2:
            return []
        # response[1] 是 claimed 列表:[(xid, fields), ...]
        claimed = response[1] or []
        messages: list[Message] = []
        for xid, fields in claimed:
            messages.append(self._parse_message(topic, xid, fields))
        return messages

    async def shutdown(self) -> None:
        # Redis 连接由 RedisContext 统一管理,这里只清空引用
        self._redis = None  # type: ignore[assignment]
        logger.debug('🛑 RedisStreamBackend 引用已清空(连接由 RedisContext 管理)')


__all__ = ['RedisStreamBackend']
