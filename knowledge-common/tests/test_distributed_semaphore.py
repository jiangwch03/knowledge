"""
DistributedSemaphore 单元测试
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_common.redis.semaphore import DistributedSemaphore


class TestCreatePool:
    """create_pool 静态方法测试"""

    @pytest.mark.asyncio
    async def test_successful_init(self):
        """正常初始化令牌池：SET NX → DELETE → RPUSH → SADD"""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.rpush = AsyncMock()
        mock_redis.sadd = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.create_pool('test:pool', size=3)

        mock_redis.set.assert_awaited_once_with('test:pool:init', '1', nx=True, ex=60)
        mock_redis.delete.assert_awaited_once_with('test:pool')
        mock_redis.rpush.assert_awaited_once_with('test:pool', '1', '1', '1')
        mock_redis.sadd.assert_awaited_once_with(DistributedSemaphore._REGISTRY_KEY, 'test:pool')

    @pytest.mark.asyncio
    async def test_skip_when_lock_exists(self):
        """其他 worker 已初始化时，SET NX 返回 False 则跳过"""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=False)

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.create_pool('test:pool', size=5)

        mock_redis.set.assert_awaited_once()
        # 不应执行后续操作
        mock_redis.delete.assert_not_called()
        mock_redis.rpush.assert_not_called()
        mock_redis.sadd.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_lock_on_failure(self):
        """SET NX 成功后填充令牌失败，应清理 init 锁"""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.rpush = AsyncMock(side_effect=RuntimeError('redis down'))
        mock_redis.delete = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            with pytest.raises(RuntimeError, match='redis down'):
                await DistributedSemaphore.create_pool('test:pool', size=3)

        # 即使在异常时也应清理 init 锁
        mock_redis.delete.assert_any_call('test:pool:init')

    @pytest.mark.asyncio
    async def test_zero_size_pool(self):
        """size=0 时创建空令牌池"""
        mock_redis = MagicMock()
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock()
        mock_redis.rpush = AsyncMock()
        mock_redis.sadd = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.create_pool('test:pool', size=0)

        # size=0 时 rpush 无参数
        mock_redis.rpush.assert_awaited_once_with('test:pool')
        mock_redis.sadd.assert_awaited_once()


class TestAcquireRelease:
    """acquire / release 实例方法测试"""

    @pytest.mark.asyncio
    async def test_acquire_blpop(self):
        """acquire 调用 BLPOP 阻塞等待令牌"""
        mock_redis = MagicMock()
        mock_redis.blpop = AsyncMock(return_value=(b'test:pool', b'1'))

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            semaphore = DistributedSemaphore(key='test:pool')
            await semaphore.acquire()

        mock_redis.blpop.assert_awaited_once_with('test:pool', timeout=0)

    @pytest.mark.asyncio
    async def test_release_lpush(self):
        """release 调用 LPUSH 归还令牌"""
        mock_redis = MagicMock()
        mock_redis.lpush = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            semaphore = DistributedSemaphore(key='test:pool')
            await semaphore.release()

        mock_redis.lpush.assert_awaited_once_with('test:pool', '1')


class TestContextManager:
    """async with 上下文管理器测试"""

    @pytest.mark.asyncio
    async def test_async_with_context(self):
        """async with 应依次 acquire → 执行体 → release"""
        mock_redis = MagicMock()
        mock_redis.blpop = AsyncMock(return_value=(b'key', b'1'))
        mock_redis.lpush = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            semaphore = DistributedSemaphore(key='test:pool')
            called = False
            async with semaphore:
                called = True

        assert called, '上下文管理器的执行体应被调用'
        mock_redis.blpop.assert_awaited_once()
        mock_redis.lpush.assert_awaited_once()


class TestDestroyPool:
    """destroy_pool 静态方法测试"""

    @pytest.mark.asyncio
    async def test_destroy_pool(self):
        """销毁令牌池：DELETE + SREM"""
        mock_redis = MagicMock()
        mock_redis.delete = AsyncMock()
        mock_redis.srem = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.destroy_pool('test:pool')

        mock_redis.delete.assert_awaited_once_with('test:pool', 'test:pool:init')
        mock_redis.srem.assert_awaited_once_with(DistributedSemaphore._REGISTRY_KEY, 'test:pool')


class TestCleanupAll:
    """cleanup_all 静态方法测试"""

    @pytest.mark.asyncio
    async def test_cleanup_with_registered_pools(self):
        """有注册队列时：批次删除所有池 + init 锁 + 注册队列"""
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={b'test:pool:a', b'test:pool:b'})
        mock_redis.delete = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.cleanup_all()

        mock_redis.smembers.assert_awaited_once_with(DistributedSemaphore._REGISTRY_KEY)
        mock_redis.delete.assert_awaited_once()

        # 验证 delete 包含所有 key（redis.delete(*names) 变参传参）
        deleted_args = mock_redis.delete.call_args[0]  # tuple of all positional args
        expected = {
            'test:pool:a',
            'test:pool:b',
            'test:pool:a:init',
            'test:pool:b:init',
            DistributedSemaphore._REGISTRY_KEY,
        }
        assert set(deleted_args) == expected

    @pytest.mark.asyncio
    async def test_cleanup_empty_registry(self):
        """注册队列为空时：仅删除注册队列"""
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value=set())
        mock_redis.delete = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.cleanup_all()

        mock_redis.smembers.assert_awaited_once()
        mock_redis.delete.assert_awaited_once_with(DistributedSemaphore._REGISTRY_KEY)

    @pytest.mark.asyncio
    async def test_cleanup_bytes_keys(self):
        """SMEMBERS 返回 bytes 时正常处理"""
        mock_redis = MagicMock()
        mock_redis.smembers = AsyncMock(return_value={b'pool:a', b'pool:b'})
        mock_redis.delete = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            await DistributedSemaphore.cleanup_all()

        mock_redis.delete.assert_awaited_once()
        deleted_args = mock_redis.delete.call_args[0]
        expected = {'pool:a', 'pool:b', 'pool:a:init', 'pool:b:init', DistributedSemaphore._REGISTRY_KEY}
        assert set(deleted_args) == expected


class TestBusinessIsolation:
    """业务隔离测试"""

    @pytest.mark.asyncio
    async def test_different_keys_for_different_business(self):
        """不同业务用不同 key，令牌池完全隔离"""
        mock_redis = MagicMock()
        mock_redis.blpop = AsyncMock(side_effect=[
            (b'pool:a', b'1'),
            (b'pool:b', b'1'),
        ])
        mock_redis.lpush = AsyncMock()

        with patch('knowledge_common.redis.semaphore.RedisContext.get_redis', return_value=mock_redis):
            sem_a = DistributedSemaphore(key='pool:a')
            sem_b = DistributedSemaphore(key='pool:b')
            await sem_a.acquire()
            await sem_b.acquire()

        # 各自操作自己的 key
        assert mock_redis.blpop.await_args_list[0].args[0] == 'pool:a'
        assert mock_redis.blpop.await_args_list[1].args[0] == 'pool:b'
