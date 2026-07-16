from enum import Enum


class SessionStatus(str, Enum):
    """Agent 会话状态枚举。"""

    ACTIVE = 'ACTIVE'
    CLOSED = 'CLOSED'
