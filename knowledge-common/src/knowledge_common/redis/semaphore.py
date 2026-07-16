"""
分布式信号量（基于 Redis BLPOP 实现真正的阻塞等待）

核心思路：用 Redis 列表作为"令牌池"，由业务方按场景独立创建。
- acquire()：通过 BLPOP 从令牌池弹出令牌，池为空时协程被 Redis 挂起
- release()：通过 LPUSH 归还令牌，Redis 自动唤醒最久等待的 BLPOP

与 asyncio.Semaphore 行为完全一致：
- acquire() 阻塞直到获取到令牌，协程被挂起，零轮询
- BLPop 按 FIFO 顺序公平唤醒等待者
- 多 worker 共享同一 Redis 令牌池

业务隔离：
- 不同业务场景使用不同的 key 创建各自的 DistributedSemaphore 实例
- 各场景的令牌池相互独立，互不干扰

注册队列（业务方无需感知）：
- create_pool() 自动将 key 注册到 Redis Set《semaphore:registry》
- 项目启动/关闭时调用 cleanup_all() 按注册队列清理所有令牌池
- 确保服务重启后无残留池状态

典型用法：
    from knowledge_common.redis import DistributedSemaphore

    # 项目启动：清理残留状态（可选）
    await DistributedSemaphore.cleanup_all()

    # 业务方：创建并初始化令牌池（保证在 acquire 之前至少调用一次）
    semaphore = DistributedSemaphore(key='semaphore:crawl_pipeline')
    await DistributedSemaphore.create_pool(key='semaphore:crawl_pipeline', size=10)

    # 使用方：阻塞等待可用槽位
    async with semaphore:
        await crawl_and_process()

    # 项目关闭：按注册队列清理所有信号量
    await DistributedSemaphore.cleanup_all()
"""

from __future__ import annotations

from redis import asyncio as aioredis

from knowledge_common.common.context import RedisContext
from knowledge_common.utils.log_util import logger


class DistributedSemaphore:
    """
    分布式信号量

    基于 Redis 列表的 BLPOP 实现分布式阻塞信号量，
    所有 worker 共享同一 Redis 令牌池。

    业务方需自行调用 create_pool() 完成令牌池初始化，
    不同场景使用不同 key 实现隔离。

    :param key: 令牌池 Redis key
    """

    # 注册队列 Redis key（维护所有已注册的令牌池 key）
    _REGISTRY_KEY = 'semaphore:registry'

    def __init__(self, key: str) -> None:
        self._key = key

    # ==================== 静态方法：令牌池管理 ====================

    @staticmethod
    async def create_pool(key: str, size: int) -> None:
        """
        创建令牌池（业务方显式调用，仅执行一次即可）

        清空并填充 size 个令牌到指定 key 的 Redis 列表中。
        使用 SET NX 确保多 worker 并发启动时仅第一个执行初始化。
        自动将 key 注册到业务队列，供 cleanup_all 清理使用。

        调用时机：服务启动时（如 app startup event），或首次使用前。

        :param key: 令牌池 Redis key
        :param size: 最大并发数（令牌数）
        """
        redis = RedisContext.get_redis()
        init_lock = f'{key}:init'
        ok = await redis.set(init_lock, '1', nx=True, ex=60)
        if not ok:
            logger.debug(f'[DistributedSemaphore] 令牌池已存在，跳过初始化: key={key}')
            return

        try:
            # 删除可能残留在 Redis 中的旧令牌（部署重启场景）
            await redis.delete(key)
            # 填充令牌
            tokens = ['1' for _ in range(size)]
            await redis.rpush(key, *tokens)
            # 注册到业务队列
            await redis.sadd(DistributedSemaphore._REGISTRY_KEY, key)
            logger.info(
                f'[DistributedSemaphore] 创建令牌池: '
                f'key={key}, size={size}'
            )
        except Exception:
            # 初始化失败时清除锁，允许后续重试
            await redis.delete(init_lock)
            raise

    @staticmethod
    async def destroy_pool(key: str) -> None:
        """
        销毁令牌池并从注册队列中移除

        :param key: 令牌池 Redis key
        """
        redis = RedisContext.get_redis()
        await redis.delete(key, f'{key}:init')
        await redis.srem(DistributedSemaphore._REGISTRY_KEY, key)
        logger.info(f'[DistributedSemaphore] 销毁令牌池: key={key}')

    @staticmethod
    async def cleanup_all() -> None:
        """
        清理所有已注册的信号量令牌池

        遍历注册队列，删除所有令牌池 key 及其 init 锁，
        最后删除注册队列自身。

        调用场景：
        - 项目启动时：清理上次部署残留的脏状态
        - 项目关闭时：优雅清理所有信号量
        """
        redis = RedisContext.get_redis()

        # 高危操作日志
        logger.info(f'[DistributedSemaphore] 开始全量清理信号量...')

        # 1. 获取所有已注册的 key
        keys = await redis.smembers(DistributedSemaphore._REGISTRY_KEY)

        if not keys:
            # 即使注册队列为空，也删除可能从旧版本遗留的 registry
            await redis.delete(DistributedSemaphore._REGISTRY_KEY)
            logger.info('[DistributedSemaphore] 无已注册信号量，跳过清理')
            return

        # 2. 收集需删除的 key（Redis SMEMBERS 返回 bytes，统一转 str）
        all_keys: set[str] = set()
        for k in keys:
            key_str = k.decode() if isinstance(k, bytes) else str(k)
            all_keys.add(key_str)
            all_keys.add(f'{key_str}:init')
        all_keys.add(DistributedSemaphore._REGISTRY_KEY)

        # 3. 批量删除
        await redis.delete(*list(all_keys))

        logger.info(
            f'[DistributedSemaphore] 全量清理完成, '
            f'cleaned={len(keys)} pools'
        )

    # ==================== 实例方法：获取/释放 ====================

    async def acquire(self) -> None:
        """
        获取信号量（阻塞直到获取到令牌）

        BLPOP 阻塞等待令牌：
        - 令牌池中有可用令牌时立即弹出并返回
        - 令牌池为空时协程被挂起，零 CPU 消耗
        - 令牌归还后 Redis 自动唤醒最久等待者（FIFO）
        """
        redis = RedisContext.get_redis()
        await redis.blpop(self._key, timeout=0)

    async def release(self) -> None:
        """
        释放信号量，归还令牌到池中

        如果此时有其他协程/worker 在 BLPOP 等待，
        Redis 会自动将令牌分配给最久等待者。
        """
        redis = RedisContext.get_redis()
        await redis.lpush(self._key, '1')

    # ==================== async with 支持 ====================

    async def __aenter__(self) -> None:
        """进入上下文，获取信号量"""
        await self.acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文，自动释放"""
        await self.release()
