from enum import Enum


class RelationType(str, Enum):
    """关联关系类型枚举"""

    CREATOR = 'creator'      # 创建者关系（会话/消息创建了任务）
    REFERENCE = 'reference'  # 引用关系（会话/消息引用了任务）
