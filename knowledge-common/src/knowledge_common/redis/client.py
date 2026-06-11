"""
Redis CRUD 封装层（透明序列化）

对 aioredis 原生 API 的二次封装，核心能力：
- 存入时自动将 Pydantic Model / dict / list 序列化为 JSON 字符串
- 取出时自动反序列化，支持通过 model 参数直接映射为 Pydantic 实例
- 覆盖 String / Hash / List / Set / ZSet 五大数据类型 + 通用操作
- Redis 客户端自动从 RedisContext 获取，无需手动传入

典型用法：
    from knowledge_common.redis import RedisClient

    # ---- String（透明序列化） ----
    await RedisClient.set('user:1', {'name': '张三', 'age': 25})
    await RedisClient.set('user:2', user_pydantic_model)
    data: dict = await RedisClient.get('user:1')
    user: UserVo = await RedisClient.get('user:2', model=UserVo)

    # ---- String（原生，不序列化） ----
    await RedisClient.set_str('token:abc', 'some_token_value', ex=3600)
    token: str = await RedisClient.get_str('token:abc')

    # ---- Hash ----
    await RedisClient.hset('user:1:profile', mapping={'name': '张三', 'age': '25'})
    profile: dict = await RedisClient.hgetall('user:1:profile')

    # ---- 通用操作 ----
    await RedisClient.delete('user:1')
    await RedisClient.expire('user:1', 3600)
    exists: bool = await RedisClient.exists('user:1')
"""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel
from redis import asyncio as aioredis

from knowledge_common.common.context import RedisContext
from knowledge_common.redis.serialization import deserialize, serialize

T = TypeVar('T', bound=BaseModel)


class RedisClient:
    """
    Redis CRUD 封装工具类

    所有方法均为 @classmethod，Redis 客户端自动从 RedisContext 获取。
    对象操作方法（set/get）自动 JSON 序列化/反序列化；
    原生字符串操作方法以 _str 后缀区分。
    """

    # ==================== 内部工具 ====================

    @classmethod
    def _get_redis(cls) -> aioredis.Redis:
        """获取 Redis 客户端"""
        return RedisContext.get_redis()

    # ==================== String（透明序列化） ====================

    @classmethod
    async def set(
        cls,
        key: str,
        value: Any,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        设置键值（自动 JSON 序列化）

        支持 Pydantic Model / dict / list / 基础类型，自动序列化为 JSON 字符串存储。

        :param key: Redis key
        :param value: 待存储的值
        :param ex: 过期时间（秒）
        :param px: 过期时间（毫秒）
        :param nx: 仅当 key 不存在时设置
        :param xx: 仅当 key 已存在时设置
        :return: 是否设置成功
        """
        redis = cls._get_redis()
        serialized = serialize(value)
        return bool(await redis.set(key, serialized, ex=ex, px=px, nx=nx, xx=xx))

    @classmethod
    async def get(cls, key: str, *, model: type[T] | None = None) -> Any:
        """
        获取值（自动 JSON 反序列化）

        :param key: Redis key
        :param model: 目标 Pydantic 类型（可选），传入时自动映射为 Model 实例
        :return: 反序列化后的值（dict / list / Model 实例），key 不存在返回 None
        """
        redis = cls._get_redis()
        raw = await redis.get(key)
        return deserialize(raw, model=model)

    @classmethod
    async def get_many(cls, keys: list[str]) -> list[Any]:
        """
        批量获取值（自动 JSON 反序列化）

        :param keys: Redis key 列表
        :return: 反序列化后的值列表（顺序与 keys 一致，不存在的为 None）
        """
        redis = cls._get_redis()
        raw_list = await redis.mget(keys)
        return [deserialize(raw) for raw in raw_list]

    @classmethod
    async def set_many(cls, mapping: dict[str, Any], *, ex: int | None = None) -> bool:
        """
        批量设置值（自动 JSON 序列化）

        :param mapping: {key: value} 映射
        :param ex: 过期时间（秒），对所有 key 生效
        :return: 是否设置成功
        """
        redis = cls._get_redis()
        serialized = {k: serialize(v) for k, v in mapping.items()}
        result = bool(await redis.mset(serialized))
        if ex is not None:
            for k in mapping:
                await redis.expire(k, ex)
        return result

    # ==================== String（原生，不序列化） ====================

    @classmethod
    async def set_str(
        cls,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        设置原生字符串值（不做序列化）

        :param key: Redis key
        :param value: 字符串值
        :param ex: 过期时间（秒）
        :param px: 过期时间（毫秒）
        :param nx: 仅当 key 不存在时设置
        :param xx: 仅当 key 已存在时设置
        :return: 是否设置成功
        """
        redis = cls._get_redis()
        return bool(await redis.set(key, value, ex=ex, px=px, nx=nx, xx=xx))

    @classmethod
    async def get_str(cls, key: str) -> str | None:
        """
        获取原生字符串值（不做反序列化）

        :param key: Redis key
        :return: 字符串值，key 不存在返回 None
        """
        redis = cls._get_redis()
        return await redis.get(key)

    @classmethod
    async def incr(cls, key: str, amount: int = 1) -> int:
        """
        自增

        :param key: Redis key
        :param amount: 自增量
        :return: 自增后的值
        """
        redis = cls._get_redis()
        return await redis.incrby(key, amount)

    # ==================== Hash ====================

    @classmethod
    async def hset(cls, name: str, key: str | None = None, value: Any = None, *, mapping: dict[str, Any] | None = None) -> int:
        """
        Hash 设置（value 自动 JSON 序列化）

        :param name: Hash key
        :param key: Hash 字段名
        :param value: Hash 字段值
        :param mapping: 批量设置 {field: value} 映射
        :return: 新增字段数
        """
        redis = cls._get_redis()
        serialized_mapping: dict[str, str] | None = None
        if mapping is not None:
            serialized_mapping = {k: serialize(v) for k, v in mapping.items()}
        serialized_value = serialize(value) if value is not None else None
        return await redis.hset(name, key, serialized_value, mapping=serialized_mapping)

    @classmethod
    async def hget(cls, name: str, key: str, *, model: type[T] | None = None) -> Any:
        """
        Hash 获取单个字段（自动 JSON 反序列化）

        :param name: Hash key
        :param key: Hash 字段名
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值
        """
        redis = cls._get_redis()
        raw = await redis.hget(name, key)
        return deserialize(raw, model=model)

    @classmethod
    async def hgetall(cls, name: str) -> dict[str, Any]:
        """
        Hash 获取所有字段（自动 JSON 反序列化）

        :param name: Hash key
        :return: {field: deserialized_value} 字典
        """
        redis = cls._get_redis()
        raw_dict = await redis.hgetall(name)
        return {k: deserialize(v) for k, v in raw_dict.items()}

    @classmethod
    async def hdel(cls, name: str, *keys: str) -> int:
        """
        Hash 删除字段

        :param name: Hash key
        :param keys: 要删除的字段名
        :return: 成功删除的字段数
        """
        redis = cls._get_redis()
        return await redis.hdel(name, *keys)

    @classmethod
    async def hexists(cls, name: str, key: str) -> bool:
        """
        Hash 判断字段是否存在

        :param name: Hash key
        :param key: Hash 字段名
        :return: 是否存在
        """
        redis = cls._get_redis()
        return bool(await redis.hexists(name, key))

    # ==================== List ====================

    @classmethod
    async def lpush(cls, name: str, *values: Any) -> int:
        """
        List 左推入（value 自动 JSON 序列化）

        :param name: List key
        :param values: 待推入的值
        :return: 推入后列表长度
        """
        redis = cls._get_redis()
        serialized = [serialize(v) for v in values]
        return await redis.lpush(name, *serialized)

    @classmethod
    async def rpush(cls, name: str, *values: Any) -> int:
        """
        List 右推入（value 自动 JSON 序列化）

        :param name: List key
        :param values: 待推入的值
        :return: 推入后列表长度
        """
        redis = cls._get_redis()
        serialized = [serialize(v) for v in values]
        return await redis.rpush(name, *serialized)

    @classmethod
    async def lpop(cls, name: str, *, model: type[T] | None = None) -> Any:
        """
        List 左弹出（自动 JSON 反序列化）

        :param name: List key
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值，列表为空返回 None
        """
        redis = cls._get_redis()
        raw = await redis.lpop(name)
        return deserialize(raw, model=model)

    @classmethod
    async def rpop(cls, name: str, *, model: type[T] | None = None) -> Any:
        """
        List 右弹出（自动 JSON 反序列化）

        :param name: List key
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值，列表为空返回 None
        """
        redis = cls._get_redis()
        raw = await redis.rpop(name)
        return deserialize(raw, model=model)

    @classmethod
    async def lrange(cls, name: str, start: int = 0, end: int = -1, *, model: type[T] | None = None) -> list[Any]:
        """
        List 范围获取（自动 JSON 反序列化）

        :param name: List key
        :param start: 起始索引
        :param end: 结束索引（-1 表示到末尾）
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值列表
        """
        redis = cls._get_redis()
        raw_list = await redis.lrange(name, start, end)
        return [deserialize(raw, model=model) for raw in raw_list]

    @classmethod
    async def llen(cls, name: str) -> int:
        """
        List 长度

        :param name: List key
        :return: 列表长度
        """
        redis = cls._get_redis()
        return await redis.llen(name)

    # ==================== Set ====================

    @classmethod
    async def sadd(cls, name: str, *values: Any) -> int:
        """
        Set 添加成员（value 自动 JSON 序列化）

        :param name: Set key
        :param values: 待添加的值
        :return: 成功添加的新成员数
        """
        redis = cls._get_redis()
        serialized = [serialize(v) for v in values]
        return await redis.sadd(name, *serialized)

    @classmethod
    async def srem(cls, name: str, *values: Any) -> int:
        """
        Set 移除成员

        :param name: Set key
        :param values: 待移除的值
        :return: 成功移除的成员数
        """
        redis = cls._get_redis()
        serialized = [serialize(v) for v in values]
        return await redis.srem(name, *serialized)

    @classmethod
    async def smembers(cls, name: str, *, model: type[T] | None = None) -> set[Any]:
        """
        Set 获取所有成员（自动 JSON 反序列化）

        :param name: Set key
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值集合
        """
        redis = cls._get_redis()
        raw_set = await redis.smembers(name)
        return {deserialize(raw, model=model) for raw in raw_set}

    @classmethod
    async def sismember(cls, name: str, value: Any) -> bool:
        """
        Set 判断成员是否存在

        :param name: Set key
        :param value: 待判断的值
        :return: 是否存在
        """
        redis = cls._get_redis()
        return bool(await redis.sismember(name, serialize(value)))

    @classmethod
    async def scard(cls, name: str) -> int:
        """
        Set 成员数量

        :param name: Set key
        :return: 成员数量
        """
        redis = cls._get_redis()
        return await redis.scard(name)

    # ==================== ZSet (Sorted Set) ====================

    @classmethod
    async def zadd(cls, name: str, mapping: dict[str, float], *, nx: bool = False, xx: bool = False) -> int:
        """
        ZSet 添加成员

        :param name: ZSet key
        :param mapping: {member: score} 映射，member 会自动 JSON 序列化
        :param nx: 仅添加不存在的成员
        :param xx: 仅更新已存在的成员
        :return: 新增/更新的成员数
        """
        redis = cls._get_redis()
        serialized = {serialize(k): v for k, v in mapping.items()}
        return await redis.zadd(name, serialized, nx=nx, xx=xx)

    @classmethod
    async def zrem(cls, name: str, *members: Any) -> int:
        """
        ZSet 移除成员

        :param name: ZSet key
        :param members: 待移除的成员
        :return: 成功移除的成员数
        """
        redis = cls._get_redis()
        serialized = [serialize(m) for m in members]
        return await redis.zrem(name, *serialized)

    @classmethod
    async def zrange(cls, name: str, start: int = 0, end: int = -1, *, model: type[T] | None = None) -> list[Any]:
        """
        ZSet 按索引范围获取成员（自动 JSON 反序列化，不含 score）

        :param name: ZSet key
        :param start: 起始索引
        :param end: 结束索引
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值列表
        """
        redis = cls._get_redis()
        raw_list = await redis.zrange(name, start, end)
        return [deserialize(raw, model=model) for raw in raw_list]

    @classmethod
    async def zrangebyscore(cls, name: str, min_score: float, max_score: float, *, model: type[T] | None = None) -> list[Any]:
        """
        ZSet 按分数范围获取成员（自动 JSON 反序列化）

        :param name: ZSet key
        :param min_score: 最小分数
        :param max_score: 最大分数
        :param model: 目标 Pydantic 类型（可选）
        :return: 反序列化后的值列表
        """
        redis = cls._get_redis()
        raw_list = await redis.zrangebyscore(name, min_score, max_score)
        return [deserialize(raw, model=model) for raw in raw_list]

    @classmethod
    async def zcard(cls, name: str) -> int:
        """
        ZSet 成员数量

        :param name: ZSet key
        :return: 成员数量
        """
        redis = cls._get_redis()
        return await redis.zcard(name)

    # ==================== 通用操作 ====================

    @classmethod
    async def delete(cls, *keys: str) -> int:
        """
        删除键

        :param keys: 要删除的 key
        :return: 成功删除的 key 数量
        """
        redis = cls._get_redis()
        return await redis.delete(*keys)

    @classmethod
    async def exists(cls, *keys: str) -> int:
        """
        判断键是否存在

        :param keys: 要判断的 key
        :return: 存在的 key 数量
        """
        redis = cls._get_redis()
        return await redis.exists(*keys)

    @classmethod
    async def expire(cls, key: str, seconds: int) -> bool:
        """
        设置过期时间

        :param key: Redis key
        :param seconds: 过期时间（秒）
        :return: 是否设置成功
        """
        redis = cls._get_redis()
        return bool(await redis.expire(key, seconds))

    @classmethod
    async def ttl(cls, key: str) -> int:
        """
        获取剩余过期时间

        :param key: Redis key
        :return: 剩余秒数（-1 永不过期，-2 key 不存在）
        """
        redis = cls._get_redis()
        return await redis.ttl(key)

    @classmethod
    async def keys(cls, pattern: str) -> list[str]:
        """
        按模式匹配获取所有 key（生产环境慎用，大数据量建议用 scan）

        :param pattern: 匹配模式（如 'sys_dict:*'）
        :return: 匹配的 key 列表
        """
        redis = cls._get_redis()
        return await redis.keys(pattern)

    @classmethod
    async def scan_iter(cls, match: str, count: int = 100) -> list[str]:
        """
        迭代式扫描 key（生产环境推荐，避免阻塞）

        :param match: 匹配模式
        :param count: 每次迭代建议返回数量
        :return: 匹配的 key 列表
        """
        redis = cls._get_redis()
        result: list[str] = []
        async for key in redis.scan_iter(match=match, count=count):
            result.append(key)
        return result

    @classmethod
    async def type(cls, key: str) -> str:
        """
        获取 key 的数据类型

        :param key: Redis key
        :return: 类型字符串（如 'string'、'hash'、'list'、'set'、'zset'）
        """
        redis = cls._get_redis()
        return await redis.type(key)
