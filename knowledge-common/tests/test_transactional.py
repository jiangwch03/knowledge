"""
注解式事务管理单元测试
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from knowledge_common.common.transactional import (
    PropagationBehavior,
    TransactionException,
    _AsyncTransactionContextManager,
    _AsyncTxContext,
    _SyncTransactionContextManager,
    _SyncTxContext,
    async_session_scope,
    get_current_session,
    get_current_session_sync,
    session_scope,
    transactional,
    transactional_sync,
    with_session,
    with_session_sync,
)


# =============================================================================
# 异步事务上下文栈测试
# =============================================================================


class TestAsyncTransactionContext:
    """异步事务上下文栈管理测试"""

    @pytest.mark.asyncio
    async def test_push_pop_current(self):
        """测试压栈、弹栈和获取当前上下文"""
        mock_session = MagicMock(spec=AsyncSession)
        ctx = _AsyncTxContext(session=mock_session, is_root=True)

        assert _AsyncTransactionContextManager.current() is None

        _AsyncTransactionContextManager.push(ctx)
        current = _AsyncTransactionContextManager.current()
        assert current is ctx
        assert current.session is mock_session

        popped = _AsyncTransactionContextManager.pop()
        assert popped is ctx
        assert _AsyncTransactionContextManager.current() is None

    @pytest.mark.asyncio
    async def test_nested_context_stack(self):
        """测试嵌套事务上下文栈"""
        mock_session1 = MagicMock(spec=AsyncSession)
        mock_session2 = MagicMock(spec=AsyncSession)

        ctx1 = _AsyncTxContext(session=mock_session1, is_root=True)
        ctx2 = _AsyncTxContext(session=mock_session2, is_root=False)

        _AsyncTransactionContextManager.push(ctx1)
        _AsyncTransactionContextManager.push(ctx2)

        assert _AsyncTransactionContextManager.current() is ctx2

        _AsyncTransactionContextManager.pop()
        assert _AsyncTransactionContextManager.current() is ctx1

        _AsyncTransactionContextManager.pop()
        assert _AsyncTransactionContextManager.current() is None

    @pytest.mark.asyncio
    async def test_is_in_transaction(self):
        """测试是否在事务中判断"""
        mock_session = MagicMock(spec=AsyncSession)
        ctx = _AsyncTxContext(session=mock_session, is_active=True)

        assert not _AsyncTransactionContextManager.is_in_transaction()

        _AsyncTransactionContextManager.push(ctx)
        assert _AsyncTransactionContextManager.is_in_transaction()

        ctx.is_active = False
        assert not _AsyncTransactionContextManager.is_in_transaction()

        _AsyncTransactionContextManager.pop()


# =============================================================================
# 同步事务上下文栈测试
# =============================================================================


class TestSyncTransactionContext:
    """同步事务上下文栈管理测试"""

    def test_push_pop_current(self):
        """测试压栈、弹栈和获取当前上下文"""
        mock_session = MagicMock(spec=Session)
        ctx = _SyncTxContext(session=mock_session, is_root=True)

        assert _SyncTransactionContextManager.current() is None

        _SyncTransactionContextManager.push(ctx)
        current = _SyncTransactionContextManager.current()
        assert current is ctx
        assert current.session is mock_session

        popped = _SyncTransactionContextManager.pop()
        assert popped is ctx
        assert _SyncTransactionContextManager.current() is None

    def test_nested_context_stack(self):
        """测试嵌套事务上下文栈"""
        mock_session1 = MagicMock(spec=Session)
        mock_session2 = MagicMock(spec=Session)

        ctx1 = _SyncTxContext(session=mock_session1, is_root=True)
        ctx2 = _SyncTxContext(session=mock_session2, is_root=False)

        _SyncTransactionContextManager.push(ctx1)
        _SyncTransactionContextManager.push(ctx2)

        assert _SyncTransactionContextManager.current() is ctx2

        _SyncTransactionContextManager.pop()
        assert _SyncTransactionContextManager.current() is ctx1

        _SyncTransactionContextManager.pop()
        assert _SyncTransactionContextManager.current() is None


# =============================================================================
# @transactional 装饰器测试
# =============================================================================


class TestTransactionalDecorator:
    """异步事务装饰器测试"""

    @pytest.mark.asyncio
    async def test_required_creates_new_transaction(self):
        """REQUIRED: 无现有事务时创建新事务"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @transactional(propagation=PropagationBehavior.REQUIRED)
            async def test_func() -> str:
                session = get_current_session()
                assert session is mock_session
                return 'success'

            result = await test_func()
            assert result == 'success'
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_required_joins_existing_transaction(self):
        """REQUIRED: 有现有事务时加入"""
        mock_session = MagicMock(spec=AsyncSession)
        ctx = _AsyncTxContext(session=mock_session, is_active=True, is_root=True)
        _AsyncTransactionContextManager.push(ctx)

        try:
            call_count = 0

            @transactional(propagation=PropagationBehavior.REQUIRED)
            async def inner_func() -> str:
                nonlocal call_count
                call_count += 1
                session = get_current_session()
                assert session is mock_session
                return 'inner'

            result = await inner_func()
            assert result == 'inner'
            assert call_count == 1
            # 内层方法不应提交（由外层提交）
        finally:
            _AsyncTransactionContextManager.pop()

    @pytest.mark.asyncio
    async def test_rollback_on_exception(self):
        """异常时自动回滚"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @transactional()
            async def failing_func() -> str:
                raise ValueError('test error')

            with pytest.raises(ValueError, match='test error'):
                await failing_func()

            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_requires_new_creates_independent_transaction(self):
        """REQUIRES_NEW: 创建独立事务"""
        outer_session = MagicMock(spec=AsyncSession)
        inner_session = AsyncMock(spec=AsyncSession)

        ctx = _AsyncTxContext(session=outer_session, is_active=True, is_root=True)
        _AsyncTransactionContextManager.push(ctx)

        try:
            with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
                mock_factory.return_value.__aenter__ = AsyncMock(return_value=inner_session)
                mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

                @transactional(propagation=PropagationBehavior.REQUIRES_NEW)
                async def inner_func() -> str:
                    session = get_current_session()
                    assert session is inner_session
                    return 'inner'

                result = await inner_func()
                assert result == 'inner'
                inner_session.commit.assert_awaited_once()
        finally:
            _AsyncTransactionContextManager.pop()

    @pytest.mark.asyncio
    async def test_never_raises_when_transaction_exists(self):
        """NEVER: 有事务时抛出异常"""
        mock_session = MagicMock(spec=AsyncSession)
        ctx = _AsyncTxContext(session=mock_session, is_active=True, is_root=True)
        _AsyncTransactionContextManager.push(ctx)

        try:
            @transactional(propagation=PropagationBehavior.NEVER)
            async def never_func() -> str:
                return 'should not reach'

            with pytest.raises(TransactionException):
                await never_func()
        finally:
            _AsyncTransactionContextManager.pop()

    @pytest.mark.asyncio
    async def test_mandatory_raises_when_no_transaction(self):
        """MANDATORY: 无事务时抛出异常"""
        @transactional(propagation=PropagationBehavior.MANDATORY)
        async def mandatory_func() -> str:
            return 'should not reach'

        with pytest.raises(TransactionException):
            await mandatory_func()

    @pytest.mark.asyncio
    async def test_rollback_for_specific_exception(self):
        """rollback_for: 指定异常才回滚"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @transactional(rollback_for=(ValueError,))
            async def func_raises_type_error() -> str:
                raise TypeError('type error')

            with pytest.raises(TypeError):
                await func_raises_type_error()

            # TypeError 不在 rollback_for 中，不应回滚
            mock_session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_rollback_for_specific_exception(self):
        """no_rollback_for: 指定异常不回滚"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @transactional(no_rollback_for=(ValueError,))
            async def func_raises_value_error() -> str:
                raise ValueError('value error')

            with pytest.raises(ValueError):
                await func_raises_value_error()

            # ValueError 在 no_rollback_for 中，不应回滚
            mock_session.rollback.assert_not_awaited()


# =============================================================================
# @transactional_sync 装饰器测试
# =============================================================================


class TestTransactionalSyncDecorator:
    """同步事务装饰器测试"""

    def test_required_creates_new_transaction(self):
        """REQUIRED: 无现有事务时创建新事务"""
        mock_session = MagicMock(spec=Session)

        with patch('knowledge_common.common.transactional.SyncSessionLocal') as mock_factory:
            mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_factory.return_value.__exit__ = MagicMock(return_value=False)

            @transactional_sync(propagation=PropagationBehavior.REQUIRED)
            def test_func() -> str:
                session = get_current_session_sync()
                assert session is mock_session
                return 'success'

            result = test_func()
            assert result == 'success'
            mock_session.commit.assert_called_once()

    def test_required_joins_existing_transaction(self):
        """REQUIRED: 有现有事务时加入"""
        mock_session = MagicMock(spec=Session)
        ctx = _SyncTxContext(session=mock_session, is_active=True, is_root=True)
        _SyncTransactionContextManager.push(ctx)

        try:
            @transactional_sync(propagation=PropagationBehavior.REQUIRED)
            def inner_func() -> str:
                session = get_current_session_sync()
                assert session is mock_session
                return 'inner'

            result = inner_func()
            assert result == 'inner'
        finally:
            _SyncTransactionContextManager.pop()

    def test_rollback_on_exception(self):
        """异常时自动回滚"""
        mock_session = MagicMock(spec=Session)

        with patch('knowledge_common.common.transactional.SyncSessionLocal') as mock_factory:
            mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_factory.return_value.__exit__ = MagicMock(return_value=False)

            @transactional_sync()
            def failing_func() -> str:
                raise ValueError('test error')

            with pytest.raises(ValueError, match='test error'):
                failing_func()

            mock_session.rollback.assert_called_once()
            mock_session.commit.assert_not_called()

    def test_never_raises_when_transaction_exists(self):
        """NEVER: 有事务时抛出异常"""
        mock_session = MagicMock(spec=Session)
        ctx = _SyncTxContext(session=mock_session, is_active=True, is_root=True)
        _SyncTransactionContextManager.push(ctx)

        try:
            @transactional_sync(propagation=PropagationBehavior.NEVER)
            def never_func() -> str:
                return 'should not reach'

            with pytest.raises(TransactionException):
                never_func()
        finally:
            _SyncTransactionContextManager.pop()

    def test_mandatory_raises_when_no_transaction(self):
        """MANDATORY: 无事务时抛出异常"""
        @transactional_sync(propagation=PropagationBehavior.MANDATORY)
        def mandatory_func() -> str:
            return 'should not reach'

        with pytest.raises(TransactionException):
            mandatory_func()


# =============================================================================
# get_current_session 测试
# =============================================================================


class TestGetCurrentSession:
    """Session 获取函数测试"""

    @pytest.mark.asyncio
    async def test_get_current_session_in_transaction(self):
        """在事务中获取 session"""
        mock_session = MagicMock(spec=AsyncSession)
        ctx = _AsyncTxContext(session=mock_session, is_active=True)
        _AsyncTransactionContextManager.push(ctx)

        try:
            session = get_current_session()
            assert session is mock_session
        finally:
            _AsyncTransactionContextManager.pop()

    @pytest.mark.asyncio
    async def test_get_current_session_outside_transaction(self):
        """事务外获取 session 应抛出异常"""
        with pytest.raises(TransactionException):
            get_current_session()

    def test_get_current_session_sync_in_transaction(self):
        """在同步事务中获取 session"""
        mock_session = MagicMock(spec=Session)
        ctx = _SyncTxContext(session=mock_session, is_active=True)
        _SyncTransactionContextManager.push(ctx)

        try:
            session = get_current_session_sync()
            assert session is mock_session
        finally:
            _SyncTransactionContextManager.pop()

    def test_get_current_session_sync_outside_transaction(self):
        """同步事务外获取 session 应抛出异常"""
        with pytest.raises(TransactionException):
            get_current_session_sync()


# =============================================================================
# with_session / session_scope 测试
# =============================================================================


class TestWithSession:
    """Session 注入装饰器和上下文管理器测试"""

    @pytest.mark.asyncio
    async def test_with_session_decorator(self):
        """@with_session 装饰器测试"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @with_session
            async def test_func() -> AsyncSession:
                return get_current_session()

            result = await test_func()
            assert result is mock_session

    @pytest.mark.asyncio
    async def test_async_session_scope(self):
        """async_session_scope 上下文管理器测试"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            async with async_session_scope() as session:
                assert session is mock_session
                assert get_current_session() is mock_session

    def test_with_session_sync_decorator(self):
        """@with_session_sync 装饰器测试"""
        mock_session = MagicMock(spec=Session)

        with patch('knowledge_common.common.transactional.SyncSessionLocal') as mock_factory:
            mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_factory.return_value.__exit__ = MagicMock(return_value=False)

            @with_session_sync
            def test_func() -> Session:
                return get_current_session_sync()

            result = test_func()
            assert result is mock_session

    def test_session_scope(self):
        """session_scope 上下文管理器测试"""
        mock_session = MagicMock(spec=Session)

        with patch('knowledge_common.common.transactional.SyncSessionLocal') as mock_factory:
            mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_factory.return_value.__exit__ = MagicMock(return_value=False)

            with session_scope() as session:
                assert session is mock_session
                assert get_current_session_sync() is mock_session


# =============================================================================
# 嵌套事务测试
# =============================================================================


class TestNestedTransaction:
    """嵌套事务测试"""

    @pytest.mark.asyncio
    async def test_async_nested_transaction_success(self):
        """异步嵌套事务：内外均成功"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @transactional(propagation=PropagationBehavior.REQUIRED)
            async def outer_func() -> str:
                inner_result = await inner_func()
                return f'outer-{inner_result}'

            @transactional(propagation=PropagationBehavior.REQUIRED)
            async def inner_func() -> str:
                return 'inner'

            result = await outer_func()
            assert result == 'outer-inner'
            # 外层提交一次即可
            mock_session.commit.assert_awaited_once()

    def test_sync_nested_transaction_success(self):
        """同步嵌套事务：内外均成功"""
        mock_session = MagicMock(spec=Session)

        with patch('knowledge_common.common.transactional.SyncSessionLocal') as mock_factory:
            mock_factory.return_value.__enter__ = MagicMock(return_value=mock_session)
            mock_factory.return_value.__exit__ = MagicMock(return_value=False)

            @transactional_sync(propagation=PropagationBehavior.REQUIRED)
            def outer_func() -> str:
                inner_result = inner_func()
                return f'outer-{inner_result}'

            @transactional_sync(propagation=PropagationBehavior.REQUIRED)
            def inner_func() -> str:
                return 'inner'

            result = outer_func()
            assert result == 'outer-inner'
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_inner_failure_rolls_back_outer(self):
        """异步嵌套事务：内层失败导致外层回滚"""
        mock_session = AsyncMock(spec=AsyncSession)

        with patch('knowledge_common.common.transactional.AsyncSessionLocal') as mock_factory:
            mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            @transactional(propagation=PropagationBehavior.REQUIRED)
            async def outer_func() -> str:
                await inner_func()
                return 'outer'

            @transactional(propagation=PropagationBehavior.REQUIRED)
            async def inner_func() -> str:
                raise ValueError('inner error')

            with pytest.raises(ValueError, match='inner error'):
                await outer_func()

            mock_session.rollback.assert_awaited_once()
            mock_session.commit.assert_not_awaited()
