"""
广播服务异常定义
"""


class BroadcastError(Exception):
    """
    广播服务统一异常

    :param message: 错误描述
    :param channel: 相关频道名（可选）
    :param cause: 原始异常（可选）
    """

    def __init__(
        self,
        message: str,
        *,
        channel: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.channel = channel
        self.cause = cause

    def __repr__(self) -> str:
        parts = [f'BroadcastError({self.args[0]!r}']
        if self.channel:
            parts.append(f', channel={self.channel!r}')
        if self.cause:
            parts.append(f', cause={self.cause!r}')
        parts.append(')')
        return ''.join(parts)


__all__ = ['BroadcastError']
