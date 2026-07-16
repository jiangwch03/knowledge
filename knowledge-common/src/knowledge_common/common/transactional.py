"""
注解式事务管理模块

提供类 Spring @Transactional 的注解式事务管理装饰器，支持异步和同步双模式。

异步 API:
    - @transactional: 异步事务装饰器
    - get_current_session(): 获取当前异步 session
    - @with_session: 异步 session 注入装饰器
    - async_session_scope(): 异步 session 上下文管理器
    - SessionContextMiddleware: FastAPI 中间件

同步 API:
    - @transactional_sync: 同步事务装饰器
    - get_current_session_sync(): 获取当前同步 session
    - @with_session_sync: 同步 session 注入装饰器
    - session_scope(): 同步 session 上下文管理器

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
from collections.abc import AsyncGenerator, Callable, Coroutine, Generator
from contextlib import asynccontextmanager, contextmanager
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
    'PropagationBehavior',
    'TransactionException',
    'TransactionTimeoutError',
    'transactional',
    'transactional_sync',
    'get_current_session',
    'get_current_session_sync',
    'with_session',
    'with_session_sync',
    'async_session_scope',
    'session_scope',
    'SessionContextMiddleware',
    'ContextVarTaskLocal',
]

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
# Session 请求/任务级上下文（非事务场景）
# =============================================================================


class _AsyncSessionContextManager:
    """异步 session 请求/任务级上下文（非事务场景）"""

    _ctx_var: ContextVarTaskLocal[AsyncSession | None] = ContextVarTaskLocal(
        'async_session_context', default=None
    )

    @classmethod
    def get(cls) -> AsyncSession | None:
        return cls._ctx_var.get()

    @classmethod
    def set(cls, session: AsyncSession | None) -> None:
        cls._ctx_var.set(session)


class _SyncSessionContextManager:
    """同步 session 任务级上下文（非事务场景）"""

    _local = threading.local()

    @classmethod
    def get(cls) -> Session | None:
        return getattr(cls._local, 'session', None)

    @classmethod
    def set(cls, session: Session | None) -> None:
        cls._local.session = session


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
    """获取当前异步事务或请求上下文中的 AsyncSession

    查找优先级：
        1. 事务上下文（@transactional 装饰的方法内）
        2. 请求/任务级上下文（FastAPI 中间件或 @with_session 内）
        3. 抛出 TransactionException

    :return: 当前 AsyncSession
    :raises TransactionException: 未在任何 session 上下文中
    """
    # 1. 优先从事务上下文获取
    tx_ctx = _AsyncTransactionContextManager.current()
    if tx_ctx and tx_ctx.is_active:
        return tx_ctx.session

    # 2. 从请求/任务级上下文获取
    session = _AsyncSessionContextManager.get()
    if session is not None:
        return session

    raise TransactionException(
        'No active async session found. Ensure you are within a @transactional, '
        '@with_session, async_session_scope, or FastAPI request context.'
    )


def get_current_session_sync() -> Session:
    """获取当前同步事务或任务上下文中的 Session

    查找优先级：
        1. 事务上下文（@transactional_sync 装饰的方法内）
        2. 任务级上下文（@with_session_sync 或 session_scope 内）
        3. 抛出 TransactionException

    :return: 当前 Session
    :raises TransactionException: 未在任何 session 上下文中
    """
    tx_ctx = _SyncTransactionContextManager.current()
    if tx_ctx and tx_ctx.is_active:
        return tx_ctx.session

    session = _SyncSessionContextManager.get()
    if session is not None:
        return session

    raise TransactionException(
        'No active sync session found. Ensure you are within a @transactional_sync, '
        '@with_session_sync, or session_scope context.'
    )


# =============================================================================
# with_session 装饰器与上下文管理器
# =============================================================================


def with_session(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """异步 session 注入装饰器

    为异步函数自动创建 AsyncSession 并注入上下文。
    适用于后台任务、定时任务、RPC 调用等非 Web 场景。
    若已有 session（事务或请求上下文），则直接复用，不再创建冗余 session。

    :param func: 被装饰的异步函数
    :return: 包装后的函数
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        # 预检：已有 session 时复用，不创建冗余 session
        try:
            get_current_session()
            return await func(*args, **kwargs)
        except TransactionException:
            pass

        async with AsyncSessionLocal() as session:
            _AsyncSessionContextManager.set(session)
            try:
                return await func(*args, **kwargs)
            finally:
                _AsyncSessionContextManager.set(None)

    return wrapper


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """异步 session 上下文管理器

    适用于需要在代码块中使用 session 的非 Web 异步场景。
    若已有 session（事务或请求上下文），则直接复用该 session。

    示例:
        >>> async with async_session_scope() as session:
        ...     result = await session.execute(select(User))
    """
    # 预检：已有 session 时直接复用
    try:
        session = get_current_session()
        yield session
        return
    except TransactionException:
        pass

    async with AsyncSessionLocal() as session:
        _AsyncSessionContextManager.set(session)
        try:
            yield session
        finally:
            _AsyncSessionContextManager.set(None)


def with_session_sync(func: Callable[..., T]) -> Callable[..., T]:
    """同步 session 注入装饰器

    为同步函数自动创建 Session 并注入上下文。
    适用于同步定时任务、脚本执行等场景。
    若已有 session（事务或任务上下文），则直接复用。

    :param func: 被装饰的同步函数
    :return: 包装后的函数
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        # 预检：已有 session 时复用
        try:
            get_current_session_sync()
            return func(*args, **kwargs)
        except TransactionException:
            pass

        with SyncSessionLocal() as session:
            _SyncSessionContextManager.set(session)
            try:
                return func(*args, **kwargs)
            finally:
                _SyncSessionContextManager.set(None)

    return wrapper


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """同步 session 上下文管理器

    适用于需要在代码块中使用 session 的同步场景。
    若已有 session（事务或任务上下文），则直接复用该 session。

    示例:
        >>> with session_scope() as session:
        ...     result = session.execute(select(User))
    """
    # 预检：已有 session 时直接复用
    try:
        session = get_current_session_sync()
        yield session
        return
    except TransactionException:
        pass

    with SyncSessionLocal() as session:
        _SyncSessionContextManager.set(session)
        try:
            yield session
        finally:
            _SyncSessionContextManager.set(None)


# =============================================================================
# FastAPI 中间件
# =============================================================================


class SessionContextMiddleware:
    """FastAPI Session 上下文中间件

    在每个请求进入时将 get_db() 创建的 AsyncSession 存入 ContextVar，
    使 get_current_session() 在非 @transactional 装饰的方法中也能返回当前请求的 session。
    若进入时已有 session（如子应用嵌套），则直接复用，不重复创建。

    注册方式:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> app.add_middleware(SessionContextMiddleware)
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        # 预检：已有 session 时复用，不重复创建
        try:
            get_current_session()
            await self.app(scope, receive, send)
            return
        except TransactionException:
            pass

        from knowledge_common.config.get_db import get_db

        db_gen = get_db()
        session = await db_gen.__anext__()
        _AsyncSessionContextManager.set(session)
        try:
            await self.app(scope, receive, send)
        finally:
            _AsyncSessionContextManager.set(None)
            try:
                await db_gen.__anext__()
            except StopAsyncIteration:
                pass
