"""
TaskLocal — 异步 Task 级本地存储

与 asyncio.Task 绑定，不会像 contextvars.ContextVar 那样
在 asyncio.create_task 创建子 Task 时自动复制快照。

类比 threading.local：threading.local 按线程隔离，TaskLocal 按 Task 隔离。

用法:
    >>> my_var = TaskLocal('my_var', default=0)
    >>> my_var.set(42)
    >>> my_var.get()
    42
"""

from __future__ import annotations

import asyncio
import weakref
from typing import Any, Generic, TypeVar

_T = TypeVar('_T')


class ContextVarTaskLocal(Generic[_T]):
    """
    异步 Task 级本地存储，不跨 Task 复制。

    原生 contextvars.ContextVar 在 asyncio.create_task 创建子 Task 时
    会自动复制当前值到子 Task（copy_context 机制）。
    ContextVarTaskLocal 使用 Task 弱引用隔离存储，子 Task 不会继承父 Task 的值。

    内部使用 WeakKeyDictionary 以 Task 对象为 key，Task 被 GC 时条目自动清理，
    避免内存泄漏和 task id 复用导致的脏数据问题。

    :param name: 变量名称（用于 repr 调试）
    :param default: 默认值（Task 中未 set 时返回该值）
    """

    def __init__(self, name: str, default: _T = None) -> None:
        self._name = name
        self._default = default
        self._storage: weakref.WeakKeyDictionary[asyncio.Task, _T] = weakref.WeakKeyDictionary()

    def get(self) -> _T:
        """获取当前 Task 的值，未 set 时返回 default"""
        task = asyncio.current_task()
        if task is None:
            return self._default
        return self._storage.get(task, self._default)

    def set(self, value: _T) -> None:
        """设置当前 Task 的值"""
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError(f"Cannot set '{self._name}' without current task")
        self._storage[task] = value

    def delete(self) -> None:
        """删除当前 Task 的值（用于显式清理，避免残留）"""
        task = asyncio.current_task()
        if task is not None:
            self._storage.pop(task, None)

    def __repr__(self) -> str:
        return f"ContextVarTaskLocal(name='{self._name}', tasks={len(self._storage)})"
