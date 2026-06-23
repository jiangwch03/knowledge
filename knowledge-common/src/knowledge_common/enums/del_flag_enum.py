from enum import Enum


class DeleteFlag(str, Enum):
    """
    删除标志枚举

    NORMAL: 正常/未删除 (0)
    DELETED: 已删除 (2)
    """

    NORMAL = '0'
    DELETED = '2'
