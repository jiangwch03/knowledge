"""
消息流服务统一异常

所有可恢复 / 业务可处理的错误基类。
业务方 `try/except MessageStreamError as e` 即可统一捕获,无需分别处理 Stream / Kafka / 后端具体异常。
"""


class MessageStreamError(Exception):
    """
    消息流服务统一异常基类

    字段:
    - topic: 出错时所在 topic(可能为 None,如 init 阶段)
    - cause: 底层原始异常引用(如有)
    """

    def __init__(self, message: str, *, topic: str | None = None, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.topic = topic
        self.cause = cause

    def __str__(self) -> str:
        base = super().__str__()
        if self.topic:
            base = f'[{self.topic}] {base}'
        if self.cause:
            base = f'{base} (cause: {self.cause!r})'
        return base
