"""DAO 基类：公开方法自动挂载隐式短事务。"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from knowledge_common.common.transactional import (
    IS_TRANSACTIONAL_ATTR,
    transactional,
    transactional_sync,
)

__all__ = ['BaseDao']


def _is_transactional_wrapped(fn: Callable[..., Any]) -> bool:
    """是否已包过事务装饰器。

    标记由 ``transactional`` / ``transactional_sync`` 在返回 wrapper 前
    ``setattr(wrapper, IS_TRANSACTIONAL_ATTR, True)`` 打上，不是 functools 自动加的。
    """
    return bool(getattr(fn, IS_TRANSACTIONAL_ATTR, False))


def _wrap_callable(fn: Callable[..., Any]) -> Callable[..., Any]:
    """给函数挂 REQUIRED 短事务；已挂过的不重复包。"""
    # 已有 IS_TRANSACTIONAL_ATTR 标记 → 说明装饰器打过了，直接复用
    if _is_transactional_wrapped(fn):
        return fn
    # async def → 异步事务；普通 def → 同步事务（包装后也会打上上述标记）
    if inspect.iscoroutinefunction(fn):
        # 异步事务装饰器
        return transactional()(fn)

    # 同步函数：同步事务装饰器
    return transactional_sync()(fn)


def _should_wrap_function(fn: Any) -> bool:
    """仅普通函数 / 协程函数需要挂事务；property 等描述符跳过。"""
    return inspect.isfunction(fn) or inspect.iscoroutinefunction(fn)


def wrap_dao_methods(cls: type) -> None:
    """为类自身定义的公开方法挂载事务装饰器（不处理继承来的方法）。

    只扫 ``cls.__dict__``：父类方法不在这里，避免重复包装。
    classmethod / staticmethod 在 ``__dict__`` 里是描述符，要先取出
    内部函数 ``__func__`` 再包，最后套回同类描述符。
    """
    # list()：遍历中会 setattr，避免 RuntimeError: dict changed size
    for name, attr in list(cls.__dict__.items()):
        # 约定：_ 开头为私有/内部方法，由公开方法间接调用，不再单独开事务
        if name.startswith('_'):
            continue
        # @classmethod：包装真正的函数，再包回 classmethod
        if isinstance(attr, classmethod):
            # @classmethod：包装真正的函数，再包回 classmethod
            fn = attr.__func__ 
            if _should_wrap_function(fn):
                setattr(cls, name, classmethod(_wrap_callable(fn)))
        # @staticmethod：同上
        elif isinstance(attr, staticmethod):
            # @staticmethod：同上
            fn = attr.__func__
            if _should_wrap_function(fn):
                setattr(cls, name, staticmethod(_wrap_callable(fn)))
        # 普通实例方法：__dict__ 里直接就是函数对象
        elif _should_wrap_function(attr):
            # 普通实例方法：__dict__ 里直接就是函数对象
            setattr(cls, name, _wrap_callable(attr))


class BaseDao:
    """持久化 DAO 基类。子类公开方法在定义时自动获得 REQUIRED 短事务。"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # 子类 class 语句执行完后自动调用；cls 是新子类，不是 BaseDao 自己
        super().__init_subclass__(**kwargs)  # 协作式继承：把钩子传给 MRO 下一环
        wrap_dao_methods(cls)  # 给该子类自身定义的公开方法挂隐式短事务
