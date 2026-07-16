from enum import Enum


class MessageRoleLangchain(str, Enum):
    """Agent 消息角色枚举，与 LangChain 消息类型序列化值对齐。"""

    HUMAN = 'human'
    AI = 'ai'
    SYSTEM = 'system'
    TOOL = 'tool'
