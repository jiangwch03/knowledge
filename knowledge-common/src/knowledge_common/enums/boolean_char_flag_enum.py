from enum import Enum


class BooleanCharFlag(str, Enum):
    """
    CHAR(1) 布尔标志枚举

    用于数据库中 CHAR(1) 类型的布尔标志字段（如 is_latest, is_ocr 等）。

    YES: 是/真 (1)
    NO: 否/假 (0)
    """

    YES = '1'
    NO = '0'
