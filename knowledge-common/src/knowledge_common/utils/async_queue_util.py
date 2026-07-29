"""异步队列工人池：固定 N 个工人从队列领任务并发执行。"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import TypeVar

from knowledge_common.utils.log_util import logger

T = TypeVar('T')


async def run_queue_workers(
    items: Sequence[T],
    concurrency: int,
    worker_fn: Callable[[T], Awaitable[None]],
) -> None:
    """固定 concurrency 个工人；谁空闲谁立刻从队列领下一件。

    任务须先全部入队再起工人；队列空时 ``get_nowait`` 抛 ``QueueEmpty`` 退出，无需哨兵。

    Args:
        items: 待处理任务列表（每项类型任意，如一批 id、一条消息等）。
        concurrency: 同时工作的工人数。
        worker_fn: 工人领到一项后执行的异步回调 ``async def fn(item: T) -> None``。
    """
    if not items:
        return
    workers = max(1, concurrency)
    # 创建队列，将 items 中的元素逐一放入队列 协程安全队列
    queue: asyncio.Queue[T] = asyncio.Queue()
    for item in items:
        queue.put_nowait(item)

    async def worker() -> None:
        # 工人循环从队列中获取任务并执行
        while True:
            try:
                item = queue.get_nowait()
            except asyncio.QueueEmpty:
                logger.info('[AsyncQueue] 队列空，工人退出')
                return
            await worker_fn(item)
    # 启动 workers 个工人，并发执行 worker 协程
    await asyncio.gather(*(worker() for _ in range(workers)))
