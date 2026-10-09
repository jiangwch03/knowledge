"""Feign 调用解包后的分页结果。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

T = TypeVar('T')


class FeignPageVo(BaseModel, Generic[T]):
    """解包对方 PageResponseModel 后的分页载体，保留业务码。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    code: int | None = None
    msg: str = ''
    rows: list[T] = Field(default_factory=list)
    total: int = 0
    page_num: int = 1
    page_size: int = 10
    has_next: bool = False


class FeignDataVo(BaseModel, Generic[T]):
    """单对象响应，保留业务码。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    code: int | None = None
    msg: str = ''
    data: T | None = None


class FeignAckVo(BaseModel):
    """无 data 的操作响应，保留业务码。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    code: int | None = None
    msg: str = ''
