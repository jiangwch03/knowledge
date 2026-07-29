from enum import Enum


class MessageRoleLangchain(str, Enum):
    """Agent 消息角色枚举。

    human/ai/system/tool 与 LangChain 消息类型对齐；
    business 为业务旁路统一落库角色（content 为 data JSON，含义由前端解析）。
    """

    HUMAN = 'human'
    AI = 'ai'
    SYSTEM = 'system'
    TOOL = 'tool'
    BUSINESS = 'business'  # 业务旁路（与 AgentSseEvent.BUSINESS 对齐）
