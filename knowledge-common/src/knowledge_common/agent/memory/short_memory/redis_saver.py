import threading
from typing import Optional

from knowledge_common.config.env import RedisConfig
from langgraph.checkpoint.redis.aio import AsyncRedisSaver


class RedisSaver:
    """
    RedisSaver 类用于将数据保存到 Redis 中。

    设计说明：
    - 采用单例模式：AsyncRedisSaver 内部通过 redis-py 的 ConnectionPool 管理 TCP 连接，
      ConnectionPool 自带 asyncio.Lock 保证协程安全，默认 max_connections=2³¹（基本无上限）。
    - 无需额外池化：AsyncRedisSaver 本身是无状态代理，真正的有状态资源（TCP 连接）已被
      ConnectionPool 内置管理。多实例反而会创建多个池，浪费 Redis 连接数。
    - 线程安全：使用双重检查锁定（DCL）保证多线程环境下只创建一个实例。
    """
    _asyncRedisSaver: Optional[AsyncRedisSaver] = None
    _lock: threading.Lock = threading.Lock()

    @staticmethod
    def _build_redis_url() -> str:
        """
        从 RedisConfig 构建 Redis 连接 URL

        :return: Redis URL 字符串
        """
        base = f'redis://{RedisConfig.redis_host}:{RedisConfig.redis_port}/{RedisConfig.redis_saver_database}'
        if RedisConfig.redis_password:
            if RedisConfig.redis_username:
                return f'redis://{RedisConfig.redis_username}:{RedisConfig.redis_password}@{RedisConfig.redis_host}:{RedisConfig.redis_port}/{RedisConfig.redis_saver_database}'
            return f'redis://:{RedisConfig.redis_password}@{RedisConfig.redis_host}:{RedisConfig.redis_port}/{RedisConfig.redis_saver_database}'
        return base

    @staticmethod
    async def get_saver() -> AsyncRedisSaver:
        """
        获取已初始化的 AsyncRedisSaver 单例实例（双重检查锁定，线程安全）

        直接构造 AsyncRedisSaver 实例并调用 asetup() 完成 Redis 索引初始化，
        不使用 from_conn_string（它是 @asynccontextmanager，只适用于 with 语句）。

        :return: AsyncRedisSaver 实例
        """
        if RedisSaver._asyncRedisSaver is None:
            with RedisSaver._lock:
                if RedisSaver._asyncRedisSaver is None:
                    redis_url = RedisSaver._build_redis_url()
                    saver = AsyncRedisSaver(redis_url=redis_url)
                    await saver.asetup()
                    await saver.aset_client_info()
                    RedisSaver._asyncRedisSaver = saver
        assert RedisSaver._asyncRedisSaver is not None
        return RedisSaver._asyncRedisSaver
