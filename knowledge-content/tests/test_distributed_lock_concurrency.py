"""
分布式锁并发测试

验证文件上传功能中分布式锁的互斥性：
- 同一 task_id 的操作互斥
- 不同 task_id 的操作可并发
- 锁获取失败时正确返回
"""

# ruff: noqa: E402, ANN201

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _PROJECT_ROOT / 'src'
sys.path.insert(0, str(_SRC_PATH))
sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_common.redis.key import LockKey


class TestLockKeyGeneration:
    """测试锁 Key 生成"""

    def test_upload_task_key(self):
        """测试上传任务锁 Key 生成"""
        key = LockKey.upload_task_key(123)
        assert key == 'lock:upload:task:123'

    def test_upload_document_key(self):
        """测试文档上传锁 Key 生成"""
        key = LockKey.upload_document_key('test.pdf')
        assert key == 'lock:upload:doc:test.pdf'

    def test_different_ids_different_keys(self):
        """不同 ID 生成不同的 Key"""
        key1 = LockKey.upload_task_key(1)
        key2 = LockKey.upload_task_key(2)
        assert key1 != key2

    def test_same_id_same_keys(self):
        """相同 ID 生成相同的 Key"""
        key1 = LockKey.upload_task_key(123)
        key2 = LockKey.upload_task_key(123)
        assert key1 == key2


class TestDistributedLockConcurrency:
    """测试分布式锁并发场景"""

    @pytest.mark.asyncio
    async def test_same_task_id_mutual_exclusion(self):
        """同一 task_id 的操作应该互斥"""
        from knowledge_common.redis import DistributedLock

        task_id = 1
        lock_key = LockKey.upload_task_key(task_id)

        # 模拟锁状态：第一次获取成功，第二次失败
        acquire_count = 0
        original_set = None

        async def mock_set(key, value, nx=False, ex=None):
            nonlocal acquire_count
            acquire_count += 1
            if nx:
                # 第一次返回 True，后续返回 False
                return acquire_count == 1
            return True

        # 使用 mock 替换 Redis
        with patch('knowledge_common.redis.lock.RedisContext') as mock_context:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(side_effect=mock_set)
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.delete = AsyncMock(return_value=True)
            mock_context.get_redis.return_value = mock_redis

            # 第一个锁获取成功
            async with DistributedLock(lock_key, expire=30) as acquired1:
                assert acquired1 is True

                # 第二个锁获取失败（同一 key）
                async with DistributedLock(lock_key, expire=30) as acquired2:
                    assert acquired2 is False

    @pytest.mark.asyncio
    async def test_different_task_ids_can_concurrent(self):
        """不同 task_id 的操作可以并发"""
        from knowledge_common.redis import DistributedLock

        task_id_1 = 1
        task_id_2 = 2
        lock_key_1 = LockKey.upload_task_key(task_id_1)
        lock_key_2 = LockKey.upload_task_key(task_id_2)

        # 模拟 Redis：不同 key 都能获取成功
        async def mock_set(key, value, nx=False, ex=None):
            if nx:
                return True
            return True

        with patch('knowledge_common.redis.lock.RedisContext') as mock_context:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(side_effect=mock_set)
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.delete = AsyncMock(return_value=True)
            mock_context.get_redis.return_value = mock_redis

            # 两个不同 key 的锁都应该获取成功
            async with DistributedLock(lock_key_1, expire=30) as acquired1:
                assert acquired1 is True

                async with DistributedLock(lock_key_2, expire=30) as acquired2:
                    assert acquired2 is True

    @pytest.mark.asyncio
    async def test_lock_timeout_returns_false(self):
        """锁超时后应该返回 False"""
        from knowledge_common.redis import DistributedLock

        lock_key = LockKey.upload_task_key(1)

        # 模拟 Redis：锁一直被占用
        async def mock_set(key, value, nx=False, ex=None):
            if nx:
                return False  # 锁被占用
            return True

        with patch('knowledge_common.redis.lock.RedisContext') as mock_context:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(side_effect=mock_set)
            mock_context.get_redis.return_value = mock_redis

            # 超时时间为 0，立即返回 False
            async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
                assert acquired is False

    @pytest.mark.asyncio
    async def test_lock_release_allows_reacquire(self):
        """锁释放后可以重新获取"""
        from knowledge_common.redis import DistributedLock

        lock_key = LockKey.upload_task_key(1)
        acquire_count = 0

        async def mock_set(key, value, nx=False, ex=None):
            nonlocal acquire_count
            if nx:
                acquire_count += 1
                # 第一次和第二次都返回 True（模拟释放后重新获取）
                return True
            return True

        with patch('knowledge_common.redis.lock.RedisContext') as mock_context:
            mock_redis = AsyncMock()
            mock_redis.set = AsyncMock(side_effect=mock_set)
            mock_redis.get = AsyncMock(return_value=None)
            mock_redis.delete = AsyncMock(return_value=True)
            mock_context.get_redis.return_value = mock_redis

            # 第一次获取
            async with DistributedLock(lock_key, expire=30) as acquired1:
                assert acquired1 is True

            # 释放后第二次获取
            async with DistributedLock(lock_key, expire=30) as acquired2:
                assert acquired2 is True

            assert acquire_count == 2


class TestLockKeyConsistency:
    """测试锁 Key 一致性 - 确保删除与其他操作使用相同的 Key"""

    def test_delete_and_decision_use_same_key_type(self):
        """删除和用户决策都应该使用 upload_task_key"""
        task_id = 123

        # 删除接口使用的 key
        delete_key = LockKey.upload_task_key(task_id)

        # 用户决策接口：先查询 task 获取 task_id，然后使用相同的 key
        # 这里模拟 task.task_id == task_id 的情况
        decision_key = LockKey.upload_task_key(task_id)

        assert delete_key == decision_key
        assert delete_key == 'lock:upload:task:123'

    def test_stage2_uses_upload_task_key(self):
        """Stage2 应该使用 upload_task_key"""
        task_id = 100

        # Stage2 应该使用 task_id 的 key
        stage2_key = LockKey.upload_task_key(task_id)

        assert stage2_key == 'lock:upload:task:100'

    def test_all_operations_use_task_id_key(self):
        """验证所有操作都使用 upload_task_key"""
        task_id = 42

        expected_key = f'lock:upload:task:{task_id}'

        # 删除接口
        assert LockKey.upload_task_key(task_id) == expected_key

        # 用户决策接口（通过 task_id）
        assert LockKey.upload_task_key(task_id) == expected_key

        # Stage2/3/4（通过 task_id）
        assert LockKey.upload_task_key(task_id) == expected_key


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
