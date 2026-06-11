"""
分布式锁抽象层

基于 Redis SET NX EX 的分布式锁实现，核心能力：
- async with 上下文管理器自动获取/释放
- 可选阻塞等待（轮询重试）
- 后台自动续期（watchdog 模式，防止长任务锁过期）
- 锁持有者校验（只有持有者能释放，防止误删他人锁）
- 支持自定义 on_lock_lost 回调

典型用法：
    from knowledge_common.redis import DistributedLock, LockKey

    # ---- 基础用法（非阻塞，拿不到就跳过） ----
    async with DistributedLock(LockKey.app_startup_key(), expire=60) as acquired:
        if not acquired:
            return  # 未抢到锁，跳过
        do_something()

    # ---- 阻塞等待（最多等 10 秒） ----
    async with DistributedLock(LockKey.custom_key('sync:job'), expire=30, timeout=10) as acquired:
        if not acquired:
            raise RuntimeError('获取锁超时')
        do_something()

    # ---- 自动续期（长任务） ----
    async with DistributedLock(LockKey.custom_key('long-task'), expire=30, renew=True) as acquired:
        if not acquired:
            return
        await very_long_running_task()  # 锁会自动续期，不会过期
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable

from redis import asyncio as aioredis

from knowledge_common.common.context import RedisContext
from knowledge_common.utils.log_util import logger


class DistributedLock:
    """
    分布式锁

    基于 Redis SET NX EX 实现，支持 async with 上下文管理。

    :param key: 锁的 Redis key（建议使用 LockKey 生成）
    :param expire: 锁过期时间（秒），默认 30
    :param timeout: 阻塞等待超时（秒），0 = 非阻塞立即返回，默认 0
    :param retry_interval: 阻塞等待轮询间隔（秒），默认 0.5
    :param renew: 是否启用自动续期，默认 False
    :param renew_interval: 续期间隔（秒），默认为 expire 的 1/3
    :param on_lock_lost: 失去锁时的回调函数（可选）
    """

    def __init__(
        self,
        key: str,
        *,
        expire: int = 30,
        timeout: float = 0,
        retry_interval: float = 0.5,
        renew: bool = False,
        renew_interval: int | None = None,
        on_lock_lost: Callable[[], None] | None = None,
    ) -> None:
        self._key = key
        self._expire = expire
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._renew = renew
        self._renew_interval = renew_interval or max(expire // 3, 1)
        self._on_lock_lost = on_lock_lost

        # 锁持有者标识（确保只有持有者能释放）
        self._holder_id = uuid.uuid4().hex
        self._acquired = False
        self._renewal_task: asyncio.Task | None = None

    @property
    def key(self) -> str:
        """锁 key"""
        return self._key

    @property
    def acquired(self) -> bool:
        """是否已获取锁"""
        return self._acquired

    def _get_redis(self) -> aioredis.Redis:
        """获取 Redis 客户端"""
        return RedisContext.get_redis()

    async def acquire(self) -> bool:
        """
        尝试获取锁

        非阻塞模式（timeout=0）：尝试一次，成功返回 True，失败返回 False。
        阻塞模式（timeout>0）：在超时内轮询重试，成功返回 True，超时返回 False。

        :return: 是否成功获取锁
        """
        redis = self._get_redis()

        if self._timeout <= 0:
            # 非阻塞：单次尝试
            self._acquired = bool(
                await redis.set(self._key, self._holder_id, nx=True, ex=self._expire)
            )
            if self._acquired:
                logger.debug(f'🔒 获取锁成功: {self._key} (holder={self._holder_id[:8]})')
                if self._renew:
                    self._start_renewal()
            return self._acquired

        # 阻塞：轮询等待
        elapsed = 0.0
        while elapsed < self._timeout:
            self._acquired = bool(
                await redis.set(self._key, self._holder_id, nx=True, ex=self._expire)
            )
            if self._acquired:
                logger.debug(f'🔒 获取锁成功: {self._key} (holder={self._holder_id[:8]}, waited={elapsed:.1f}s)')
                if self._renew:
                    self._start_renewal()
                return True
            await asyncio.sleep(self._retry_interval)
            elapsed += self._retry_interval

        logger.warning(f'🔒 获取锁超时: {self._key} (timeout={self._timeout}s)')
        return False

    async def release(self) -> bool:
        """
        释放锁

        仅当当前实例是锁持有者时才释放（Lua 脚本原子校验），防止误删他人锁。

        :return: 是否成功释放
        """
        self._stop_renewal()
        if not self._acquired:
            return False

        redis = self._get_redis()
        # Lua 脚本：原子校验 holder_id 并删除，防止释放他人持有的锁
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await redis.eval(lua_script, 1, self._key, self._holder_id)
        self._acquired = False
        if result:
            logger.debug(f'🔓 释放锁成功: {self._key} (holder={self._holder_id[:8]})')
        else:
            logger.warning(f'🔓 释放锁失败（锁已不属于当前持有者）: {self._key}')
        return bool(result)

    def _start_renewal(self) -> None:
        """启动后台续期任务"""
        self._renewal_task = asyncio.create_task(self._renewal_loop())

    def _stop_renewal(self) -> None:
        """停止后台续期任务"""
        if self._renewal_task is not None:
            self._renewal_task.cancel()
            self._renewal_task = None

    async def _renewal_loop(self) -> None:
        """
        后台续期循环

        每隔 renew_interval 秒检查锁是否仍属于当前持有者：
        - 是 → EXPIRE 续期
        - 否 → 触发 on_lock_lost 回调并退出
        """
        try:
            while True:
                await asyncio.sleep(self._renew_interval)
                redis = self._get_redis()
                current_holder = await redis.get(self._key)
                if current_holder == self._holder_id:
                    await redis.expire(self._key, self._expire)
                    logger.debug(f'🔄 锁续期成功: {self._key}')
                else:
                    logger.warning(f'🔒 锁已丢失: {self._key} (holder={self._holder_id[:8]})')
                    self._acquired = False
                    if self._on_lock_lost:
                        self._on_lock_lost()
                    break
        except asyncio.CancelledError:
            # 正常取消（release 时调用 _stop_renewal）
            pass

    # ==================== async with 支持 ====================

    async def __aenter__(self) -> bool:
        """
        进入锁上下文

        :return: 是否成功获取锁
        """
        return await self.acquire()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出锁上下文，自动释放"""
        await self.release()
