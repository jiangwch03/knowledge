"""
消息流服务消息结构

字段命名对齐 Kafka,保证切 Kafka 时业务代码零修改。
- Stream 后端:把 xid 映射为 offset,fields 拆为 headers + value
- Kafka 后端:直接用原生字段

兼容别名:
- msg.stream  ≡ msg.topic
- msg.payload ≡ msg.value
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """
    消息结构(Kafka 风格,中间件无关)

    字段:
    - topic: 主题
    - key: 业务键(Kafka partition key / Stream 业务过滤键)
    - value: 载荷
    - headers: 头部元数据
    - timestamp: 毫秒时间戳
    - offset: 消息位置(Stream 格式 "1234-0" / Kafka offset 字符串化)
    - partition: 分区号(Stream 无分区,值为 None)
    """

    topic: str
    key: str | None = None
    value: Any = None
    headers: dict[str, Any] = field(default_factory=dict)
    timestamp: int = 0
    offset: str = ''
    partition: int | None = None

    # --- 平滑过渡别名(老代码可读旧名) ---
    @property
    def stream(self) -> str:
        return self.topic

    @property
    def payload(self) -> Any:
        return self.value

    def __repr__(self) -> str:
        return (
            f'<Message topic={self.topic!r} key={self.key!r} '
            f'offset={self.offset!r} partition={self.partition} '
            f'timestamp={self.timestamp}>'
        )
