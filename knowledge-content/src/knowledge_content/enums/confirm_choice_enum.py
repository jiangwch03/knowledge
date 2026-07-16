from enum import Enum


class ConfirmChoice(str, Enum):
    """
    用户确认类弹窗选择枚举

    LLM 固定输出 yes/no 模板，供 URL 路由节点判断用户确认/取消。
    """

    YES = 'yes'  # 用户确认
    NO = 'no'  # 用户取消
