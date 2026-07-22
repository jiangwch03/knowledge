"""
雪花算法 ID 生成工具

结构（64 bit）：
  1 bit  符号位（固定 0）
  41 bit 毫秒时间戳（相对自定义纪元）
  5 bit  数据中心 ID
  5 bit  机器 ID
  12 bit 序列号
"""

from __future__ import annotations

import os
import threading
import time


class SnowflakeUtil:
    """线程安全的雪花 ID 生成器。"""

    # 自定义纪元：2024-01-01 00:00:00 UTC，拉长可用年限
    _EPOCH_MS = 1_704_067_200_000

    _WORKER_ID_BITS = 5
    _DATACENTER_ID_BITS = 5
    _SEQUENCE_BITS = 12

    _MAX_WORKER_ID = (1 << _WORKER_ID_BITS) - 1
    _MAX_DATACENTER_ID = (1 << _DATACENTER_ID_BITS) - 1
    _SEQUENCE_MASK = (1 << _SEQUENCE_BITS) - 1

    _WORKER_ID_SHIFT = _SEQUENCE_BITS
    _DATACENTER_ID_SHIFT = _SEQUENCE_BITS + _WORKER_ID_BITS
    _TIMESTAMP_SHIFT = _SEQUENCE_BITS + _WORKER_ID_BITS + _DATACENTER_ID_BITS

    _lock = threading.Lock()
    _sequence = 0
    _last_timestamp = -1

    # 默认：datacenter=0，worker 取 pid 低位，保证同机多进程尽量错开
    _datacenter_id = 0
    _worker_id = os.getpid() & _MAX_WORKER_ID

    @classmethod
    def configure(cls, *, datacenter_id: int = 0, worker_id: int | None = None) -> None:
        """
        可选：显式配置数据中心 / 机器 ID（启动时调用一次即可）。

        :param datacenter_id: 0 ~ 31
        :param worker_id: 0 ~ 31；None 则沿用 pid 派生值
        """
        if not 0 <= datacenter_id <= cls._MAX_DATACENTER_ID:
            raise ValueError(f'datacenter_id must be between 0 and {cls._MAX_DATACENTER_ID}')
        if worker_id is not None and not 0 <= worker_id <= cls._MAX_WORKER_ID:
            raise ValueError(f'worker_id must be between 0 and {cls._MAX_WORKER_ID}')

        with cls._lock:
            cls._datacenter_id = datacenter_id
            if worker_id is not None:
                cls._worker_id = worker_id

    @classmethod
    def next_id(cls) -> str:
        """生成下一个雪花 ID（十进制字符串，便于落库 String 字段）。"""
        return str(cls.next_id_int())

    @classmethod
    def next_id_int(cls) -> int:
        """生成下一个雪花 ID（int）。"""
        with cls._lock:
            timestamp = cls._current_millis()

            if timestamp < cls._last_timestamp:
                # 时钟回拨：短暂等待追上上次时间戳
                timestamp = cls._wait_until(cls._last_timestamp)

            if timestamp == cls._last_timestamp:
                cls._sequence = (cls._sequence + 1) & cls._SEQUENCE_MASK
                if cls._sequence == 0:
                    timestamp = cls._wait_until(cls._last_timestamp)
            else:
                cls._sequence = 0

            cls._last_timestamp = timestamp

            return (
                ((timestamp - cls._EPOCH_MS) << cls._TIMESTAMP_SHIFT)
                | (cls._datacenter_id << cls._DATACENTER_ID_SHIFT)
                | (cls._worker_id << cls._WORKER_ID_SHIFT)
                | cls._sequence
            )

    @classmethod
    def _current_millis(cls) -> int:
        return int(time.time() * 1000)

    @classmethod
    def _wait_until(cls, last_timestamp: int) -> int:
        timestamp = cls._current_millis()
        while timestamp <= last_timestamp:
            timestamp = cls._current_millis()
        return timestamp
