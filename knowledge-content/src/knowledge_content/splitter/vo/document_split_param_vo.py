import re

from pydantic import BaseModel, Field, model_validator

from knowledge_common.exceptions.exception import ServiceException
from knowledge_content.enums.split_type_enum import SplitType


class DocumentSplitParamVo(BaseModel):
    """切分策略入参"""

    split_type: SplitType  # 切分策略类型
    chunk_size: int = Field(..., gt=0)  # 分块最大长度（字符数），必须大于 0
    overlap: int = Field(default=0, ge=0)  # 相邻分块重叠长度，必须小于 chunk_size；SMART 策略会自动设为 chunk_size 的 10%
    title_level: int | None = None  # TITLE 策略专用：标题层级（1~6，对应 Markdown # ~ ######）
    separator: str | None = None  # SEPARATOR 策略专用：字面量分隔符（来自系统字典 document_split_separator）
    regex: str | None = None  # REGEX 策略专用：切分正则表达式

    @model_validator(mode='after')
    def validate_strategy_params(self) -> 'DocumentSplitParamVo':
        """按策略校验/补全参数：SMART 自动补 overlap，其余策略做字段合法性检查。"""
        # SMART：固定使用 10% overlap，跳过后续通用校验
        if self.split_type == SplitType.SMART:
            object.__setattr__(self, 'overlap', int(self.chunk_size * 0.1))
            return self

        # 重叠长度不能大于等于分块长度，否则无有效推进
        if self.overlap >= self.chunk_size:
            raise ServiceException(message='重叠长度必须小于块大小')

        # TITLE：必须指定有效标题层级
        if self.split_type == SplitType.TITLE:
            if self.title_level is None or not 1 <= self.title_level <= 6:
                raise ServiceException(message='标题层级切分时，标题层级须为 1–6')

        # SEPARATOR：须选择字典中的字面量分隔符（前端下拉；此处仅校验非空）
        if self.split_type == SplitType.SEPARATOR:
            if self.separator is None or self.separator == '':
                raise ServiceException(message='分隔符切分时，分隔符不能为空')

        # REGEX：正则必填且须可编译
        if self.split_type == SplitType.REGEX:
            if not self.regex:
                raise ServiceException(message='正则切分时，正则表达式不能为空')
            try:
                re.compile(self.regex)
            except re.error as exc:
                raise ServiceException(message=f'正则表达式无效：{exc}') from exc

        return self
