from enum import Enum


class ParseDecisionAction(str, Enum):
    """
    解析决策动作枚举

    RETRY: 重试
    DELETE: 删除
    """

    RETRY = 'retry'
    DELETE = 'delete'
