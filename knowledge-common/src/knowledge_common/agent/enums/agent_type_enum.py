from enum import Enum


class AgentType(str, Enum):
    """Agent 类型枚举，用于会话/消息多 Agent 隔离。"""

    WEB_CRAWLER = 'web_crawler'
