from enum import Enum


class SplitType(str, Enum):
    """文档切分策略（value=存储码，label=前端展示名）"""

    TITLE = ('TITLE', '标题层级切分')  # 按 Markdown 标题层级切分
    LENGTH = ('LENGTH', '固定长度切分')  # 按固定长度切分
    SEPARATOR = ('SEPARATOR', '分隔符切分')  # 按字典中的单个字面量分隔符切分
    REGEX = ('REGEX', '正则切分')  # 按正则表达式切分
    SMART = ('SMART', '智能标题切分')  # 智能切分（标题+行级，重叠默认 10%）

    def __new__(cls, value: str, label: str) -> 'SplitType':
        obj = str.__new__(cls, value)
        obj._value_ = value
        obj.label = label
        return obj

    @classmethod
    def label_of(cls, code: str | None) -> str:
        """按 code 取展示名；未知码原样返回。"""
        if not code:
            return '-'
        try:
            return cls(code).label
        except ValueError:
            return code
