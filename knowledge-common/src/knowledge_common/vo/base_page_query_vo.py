from pydantic import BaseModel, Field


class BasePageQueryModel(BaseModel):
    """
    分页查询基类
    """

    page_num: int = Field(default=1, description='当前页码')
    page_size: int = Field(default=10, description='每页记录数')


__all__ = [
    'BasePageQueryModel',
]
