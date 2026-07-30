"""
注解式事务管理模块

提供类 Spring @Transactional 的注解式事务管理装饰器，支持异步和同步双模式。
Session 仅由事务边界提供（Service @transactional 或 DAO / PageUtil 隐式短事务）。

异步 API:
    - @transactional: 异步事务装饰器
    - get_current_session(): 获取当前异步事务 session

同步 API:
    - @transactional_sync: 同步事务装饰器
    - get_current_session_sync(): 获取当前同步事务 session

示例:
    >>> @transactional
    ... async def create_user(user: UserModel) -> CrudResponseModel:
    ...     session = get_current_session()
    ...     session.add(user)
    ...     return CrudResponseModel(is_success=True, message='创建成功')

    >>> @transactional_sync
    ... def add_log(log: LogModel) -> CrudResponseModel:
    ...     session = get_current_session_sync()
    ...     session.add(log)
    ...     return CrudResponseModel(is_success=True, message='记录成功')
"""

from __future__ import annotations

import asyncio
import functools
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from knowledge_common.common.context_var_task_local import ContextVarTaskLocal
from knowledge_common.config.database import AsyncSessionLocal, SyncSessionLocal

__all__ = [
    'IS_TRANSACTIONAL_ATTR',
    'PropagationBehavior',
    'TransactionException',
    'TransactionTimeoutError',
    'transactional',
    'transactional_sync',
    'get_current_session',
    'get_current_session_sync',
    'ContextVarTaskLocal',
]

# 装饰器 wrapper 上的标记属性名；BaseDao 等据此识别「已包装」，避免重复挂事务
IS_TRANSACTIONAL_ATTR = '__is_transactional__'

# =============================================================================
# 基础类型与枚举
# =============================================================================


class PropagationBehavior(Enum):
    """事务传播行为枚举"""

    REQUIRED = 'REQUIRED'  # 默认：有则加入，无则新建
    REQUIRES_NEW = 'REQUIRES_NEW'  # 新建独立事务，挂起当前事务
    SUPPORTS = 'SUPPORTS'  # 有则加入，无则无事务运行
    NOT_SUPPORTED = 'NOT_SUPPORTED'  # 无事务运行，挂起当前事务
    NEVER = 'NEVER'  # 无事务运行，有则抛异常
    MANDATORY = 'MANDATORY'  # 必须有事务，无则抛异常
    NESTED = 'NESTED'  # 在当前事务中创建 savepoint


class TransactionException(Exception):
    """事务管理异常"""

    pass


class TransactionTimeoutError(TransactionException):
    """事务超时异常"""

    pass


# =============================================================================
# 异步事务上下文（基于 ContextVar）
# =============================================================================


@dataclass
class _AsyncTxContext:
    """单个异步事务上下文"""

    session: AsyncSession
    is_active: bool = True
    is_read_only: bool = False
    is_root: bool = False  # 是否为最外层事务
    savepoint_name: str | None = None  # NESTED 模式下的 savepoint 名称


class _AsyncTransactionContextManager:
    """异步事务上下文栈管理器（ContextVarTaskLocal 实现）

    使用 ContextVarTaskLocal（按 Task ID 隔离）而非原生 ContextVar，
    避免 asyncio.create_task 创建子 Task 时自动复制父 Task 的事务上下文，
    导致子 Task 意外继承父 Task 的 session，引发 'prepared' state 等异常。
    同一 Task 内的嵌套 @transactional 调用仍通过同一 list 栈正确传播。
    """

    _ctx_var: ContextVarTaskLocal[list[_AsyncTxContext] | None] = ContextVarTaskLocal(
        'async_transaction_context', default=None
    )

    @classmethod
    def get_stack(cls) -> list[_AsyncTxContext]:
        """获取当前 Task 的事务上下文栈（未初始化时返回新的空列表）"""
        stack = cls._ctx_var.get()
        if stack is None:
            return []
        return stack

    @classmethod
    def push(cls, ctx: _AsyncTxContext) -> None:
        """将事务上下文压入栈"""
        stack = cls._ctx_var.get()
        if stack is None:
            stack = []
        stack.append(ctx)
        cls._ctx_var.set(stack)

    @classmethod
    def pop(cls) -> _AsyncTxContext | None:
        """弹出栈顶事务上下文"""
        stack = cls._ctx_var.get()
        if not stack:
            return None
        ctx = stack.pop()
        cls._ctx_var.set(stack)
        return ctx

    @classmethod
    def current(cls) -> _AsyncTxContext | None:
        """获取当前活跃的事务上下文（栈顶）"""
        stack = cls._ctx_var.get()
        if not stack:
            return None
        return stack[-1]

    @classmethod
    def is_in_transaction(cls) -> bool:
        """当前是否在事务中"""
        ctx = cls.current()
        return ctx is not None and ctx.is_active


# =============================================================================
# 同步事务上下文（基于 threading.local）
# =============================================================================


@dataclass
class _SyncTxContext:
    """单个同步事务上下文"""

    session: Session
    is_active: bool = True
    is_read_only: bool = False
    is_root: bool = False
    savepoint_name: str | None = None


class _SyncTransactionContextManager:
    """同步事务上下文栈管理器（threading.local 实现）"""

    _local = threading.local()

    @classmethod
    def _get_stack(cls) -> list[_SyncTxContext]:
        if not hasattr(cls._local, 'stack'):
            cls._local.stack = []
        return cls._local.stack

    @classmethod
    def push(cls, ctx: _SyncTxContext) -> None:
        cls._get_stack().append(ctx)

    @classmethod
    def pop(cls) -> _SyncTxContext | None:
        stack = cls._get_stack()
        if not stack:
            return None
        return stack.pop()

    @classmethod
    def current(cls) -> _SyncTxContext | None:
        stack = cls._get_stack()
        if not stack:
            return None
        return stack[-1]

    @classmethod
    def is_in_transaction(cls) -> bool:
        ctx = cls.current()
        return ctx is not None and ctx.is_active


# =============================================================================
# 异常类型检查工具
# =============================================================================


def _should_rollback(exc: Exception, rollback_for: tuple[type[Exception], ...], no_rollback_for: tuple[type[Exception], ...]) -> bool:
    """判断异常是否应触发回滚"""
    # 如果在 no_rollback_for 中，不回滚
    for exc_type in no_rollback_for:
        if isinstance(exc, exc_type):
            return False
    # 如果指定了 rollback_for，只在其中才回滚
    if rollback_for:
        for exc_type in rollback_for:
            if isinstance(exc, exc_type):
                return True
        return False
    # 默认：所有 Exception 都回滚
    return True


# =============================================================================
# 异步事务装饰器核心
# =============================================================================


T = TypeVar('T')


def transactional(
    propagation: PropagationBehavior = PropagationBehavior.REQUIRED,
    isolation: str | None = None,
    read_only: bool = False,
    timeout: int | None = None,
    rollback_for: tuple[type[Exception], ...] | None = None,
    no_rollback_for: tuple[type[Exception], ...] | None = None,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """异步事务装饰器

    :param propagation: 事务传播行为，默认 REQUIRED
    :param isolation: 事务隔离级别（未实现，预留参数）
    :param read_only: 是否为只读事务
    :param timeout: 事务超时时间（秒），None 表示不限制
    :param rollback_for: 指定触发回滚的异常类型，None 表示所有异常都回滚
    :param no_rollback_for: 指定不触发回滚的异常类型
    :return: 装饰器函数
    """
    rollback_for = rollback_for or ()
    no_rollback_for = no_rollback_for or ()

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            tx_stack = _AsyncTransactionContextManager.get_stack()
            current_tx = _AsyncTransactionContextManager.current()

            # 根据传播行为决定如何处理
            if propagation == PropagationBehavior.REQUIRED:
                if current_tx and current_tx.is_active:
                    # 加入现有事务
                    return await func(*args, **kwargs)
                # 新建事务
                return await _run_in_async_transaction(
                    func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for, is_root=True
                )

            elif propagation == PropagationBehavior.REQUIRES_NEW:
                # 挂起当前事务，新建独立事务
                return await _run_in_async_transaction(
                    func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for, is_root=True
                )

            elif propagation == PropagationBehavior.SUPPORTS:
                if current_tx and current_tx.is_active:
                    return await func(*args, **kwargs)
                # 无事务运行
                return await func(*args, **kwargs)

            elif propagation == PropagationBehavior.NOT_SUPPORTED:
                if current_tx and current_tx.is_active:
                    # 挂起当前事务，无事务运行
                    _AsyncTransactionContextManager.pop()
                    try:
                        return await func(*args, **kwargs)
                    finally:
                        _AsyncTransactionContextManager.push(current_tx)
                return await func(*args, **kwargs)

            elif propagation == PropagationBehavior.NEVER:
                if current_tx and current_tx.is_active:
                    raise TransactionException(
                        f'Propagation NEVER but existing transaction found when calling {func.__name__}'
                    )
                return await func(*args, **kwargs)

            elif propagation == PropagationBehavior.MANDATORY:
                if not current_tx or not current_tx.is_active:
                    raise TransactionException(
                        f'Propagation MANDATORY but no existing transaction found when calling {func.__name__}'
                    )
                return await func(*args, **kwargs)

            elif propagation == PropagationBehavior.NESTED:
                if current_tx and current_tx.is_active:
                    # 在现有事务中创建 savepoint
                    return await _run_in_async_nested_transaction(
                        func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for
                    )
                # 无现有事务，行为同 REQUIRED
                return await _run_in_async_transaction(
                    func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for, is_root=True
                )

            else:
                raise TransactionException(f'Unknown propagation behavior: {propagation}')

        setattr(wrapper, IS_TRANSACTIONAL_ATTR, True)
        return wrapper

    return decorator


async def _run_in_async_transaction(
    func: Callable[..., Coroutine[Any, Any, T]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    read_only: bool,
    timeout: int | None,
    rollback_for: tuple[type[Exception], ...],
    no_rollback_for: tuple[type[Exception], ...],
    is_root: bool = True,
) -> T:
    """在新建异步事务中执行函数"""
    async with AsyncSessionLocal() as session:
        tx_ctx = _AsyncTxContext(
            session=session,
            is_active=True,
            is_read_only=read_only,
            is_root=is_root,
        )
        _AsyncTransactionContextManager.push(tx_ctx)
        try:
            if read_only:
                await session.execute(text('SET TRANSACTION READ ONLY'))

            if timeout:
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
            else:
                result = await func(*args, **kwargs)

            await session.commit()
            tx_ctx.is_active = False
            return result

        except Exception as exc:
            if _should_rollback(exc, rollback_for, no_rollback_for):
                await session.rollback()
            tx_ctx.is_active = False
            raise
        finally:
            _AsyncTransactionContextManager.pop()


async def _run_in_async_nested_transaction(
    func: Callable[..., Coroutine[Any, Any, T]],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    read_only: bool,
    timeout: int | None,
    rollback_for: tuple[type[Exception], ...],
    no_rollback_for: tuple[type[Exception], ...],
) -> T:
    """在现有异步事务中通过 savepoint 执行函数"""
    current_tx = _AsyncTransactionContextManager.current()
    if current_tx is None:
        raise TransactionException('NESTED propagation requires an existing transaction')

    session = current_tx.session
    savepoint_name = f'sp_{uuid4().hex[:16]}'
    await session.execute(text(f'SAVEPOINT {savepoint_name}'))

    tx_ctx = _AsyncTxContext(
        session=session,
        is_active=True,
        is_read_only=read_only,
        is_root=False,
        savepoint_name=savepoint_name,
    )
    _AsyncTransactionContextManager.push(tx_ctx)
    try:
        if timeout:
            result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
        else:
            result = await func(*args, **kwargs)

        await session.execute(text(f'RELEASE SAVEPOINT {savepoint_name}'))
        tx_ctx.is_active = False
        return result

    except Exception as exc:
        if _should_rollback(exc, rollback_for, no_rollback_for):
            await session.execute(text(f'ROLLBACK TO SAVEPOINT {savepoint_name}'))
        tx_ctx.is_active = False
        raise
    finally:
        _AsyncTransactionContextManager.pop()


# =============================================================================
# 同步事务装饰器核心
# =============================================================================


def transactional_sync(
    propagation: PropagationBehavior = PropagationBehavior.REQUIRED,
    isolation: str | None = None,
    read_only: bool = False,
    timeout: int | None = None,
    rollback_for: tuple[type[Exception], ...] | None = None,
    no_rollback_for: tuple[type[Exception], ...] | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """同步事务装饰器

    :param propagation: 事务传播行为，默认 REQUIRED
    :param isolation: 事务隔离级别（未实现，预留参数）
    :param read_only: 是否为只读事务
    :param timeout: 事务超时时间（秒），None 表示不限制
    :param rollback_for: 指定触发回滚的异常类型，None 表示所有异常都回滚
    :param no_rollback_for: 指定不触发回滚的异常类型
    :return: 装饰器函数
    """
    rollback_for = rollback_for or ()
    no_rollback_for = no_rollback_for or ()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            tx_stack = _SyncTransactionContextManager._get_stack()
            current_tx = _SyncTransactionContextManager.current()

            if propagation == PropagationBehavior.REQUIRED:
                if current_tx and current_tx.is_active:
                    return func(*args, **kwargs)
                return _run_in_sync_transaction(
                    func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for, is_root=True
                )

            elif propagation == PropagationBehavior.REQUIRES_NEW:
                return _run_in_sync_transaction(
                    func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for, is_root=True
                )

            elif propagation == PropagationBehavior.SUPPORTS:
                if current_tx and current_tx.is_active:
                    return func(*args, **kwargs)
                return func(*args, **kwargs)

            elif propagation == PropagationBehavior.NOT_SUPPORTED:
                if current_tx and current_tx.is_active:
                    _SyncTransactionContextManager.pop()
                    try:
                        return func(*args, **kwargs)
                    finally:
                        _SyncTransactionContextManager.push(current_tx)
                return func(*args, **kwargs)

            elif propagation == PropagationBehavior.NEVER:
                if current_tx and current_tx.is_active:
                    raise TransactionException(
                        f'Propagation NEVER but existing transaction found when calling {func.__name__}'
                    )
                return func(*args, **kwargs)

            elif propagation == PropagationBehavior.MANDATORY:
                if not current_tx or not current_tx.is_active:
                    raise TransactionException(
                        f'Propagation MANDATORY but no existing transaction found when calling {func.__name__}'
                    )
                return func(*args, **kwargs)

            elif propagation == PropagationBehavior.NESTED:
                if current_tx and current_tx.is_active:
                    return _run_in_sync_nested_transaction(
                        func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for
                    )
                return _run_in_sync_transaction(
                    func, args, kwargs, read_only, timeout, rollback_for, no_rollback_for, is_root=True
                )

            else:
                raise TransactionException(f'Unknown propagation behavior: {propagation}')

        setattr(wrapper, IS_TRANSACTIONAL_ATTR, True)
        return wrapper

    return decorator


def _run_in_sync_transaction(
    func: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    read_only: bool,
    timeout: int | None,
    rollback_for: tuple[type[Exception], ...],
    no_rollback_for: tuple[type[Exception], ...],
    is_root: bool = True,
) -> T:
    """在新建同步事务中执行函数"""
    with SyncSessionLocal() as session:
        tx_ctx = _SyncTxContext(
            session=session,
            is_active=True,
            is_read_only=read_only,
            is_root=is_root,
        )
        _SyncTransactionContextManager.push(tx_ctx)
        try:
            if read_only:
                session.execute(text('SET TRANSACTION READ ONLY'))

            # TODO: 同步超时实现（signal / threading.Timer）
            result = func(*args, **kwargs)

            session.commit()
            tx_ctx.is_active = False
            return result

        except Exception as exc:
            if _should_rollback(exc, rollback_for, no_rollback_for):
                session.rollback()
            tx_ctx.is_active = False
            raise
        finally:
            _SyncTransactionContextManager.pop()


def _run_in_sync_nested_transaction(
    func: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    read_only: bool,
    timeout: int | None,
    rollback_for: tuple[type[Exception], ...],
    no_rollback_for: tuple[type[Exception], ...],
) -> T:
    """在现有同步事务中通过 savepoint 执行函数"""
    current_tx = _SyncTransactionContextManager.current()
    if current_tx is None:
        raise TransactionException('NESTED propagation requires an existing transaction')

    session = current_tx.session
    savepoint_name = f'sp_{uuid4().hex[:16]}'
    session.execute(text(f'SAVEPOINT {savepoint_name}'))

    tx_ctx = _SyncTxContext(
        session=session,
        is_active=True,
        is_read_only=read_only,
        is_root=False,
        savepoint_name=savepoint_name,
    )
    _SyncTransactionContextManager.push(tx_ctx)
    try:
        result = func(*args, **kwargs)

        session.execute(text(f'RELEASE SAVEPOINT {savepoint_name}'))
        tx_ctx.is_active = False
        return result

    except Exception as exc:
        if _should_rollback(exc, rollback_for, no_rollback_for):
            session.execute(text(f'ROLLBACK TO SAVEPOINT {savepoint_name}'))
        tx_ctx.is_active = False
        raise
    finally:
        _SyncTransactionContextManager.pop()


# =============================================================================
# Session 获取函数
# =============================================================================


def get_current_session() -> AsyncSession:
    """获取当前异步事务上下文中的 AsyncSession

    :return: 当前 AsyncSession
    :raises TransactionException: 未在活跃异步事务中
    """
    tx_ctx = _AsyncTransactionContextManager.current()
    if tx_ctx and tx_ctx.is_active:
        return tx_ctx.session

    raise TransactionException(
        'No active async session found. Ensure you are within a @transactional '
        'context (Service annotation, BaseDao implicit short transaction, or PageUtil.paginate).'
    )


def get_current_session_sync() -> Session:
    """获取当前同步事务上下文中的 Session

    :return: 当前 Session
    :raises TransactionException: 未在活跃同步事务中
    """
    tx_ctx = _SyncTransactionContextManager.current()
    if tx_ctx and tx_ctx.is_active:
        return tx_ctx.session

    raise TransactionException(
        'No active sync session found. Ensure you are within a @transactional_sync '
        'context (Service annotation or BaseDao implicit short transaction).'
    )
