from typing import Generic, TypeVar
T = TypeVar('T')
from pydantic import BaseModel, Field


class MinerUBaseRespVo(BaseModel,Generic[T]):
    """解析进度"""

    code: int | None = Field(None, description='接口状态码，成功： 0')
    msg: int | None = Field(None, description='接口处理信息，成功："ok"')
    trace_id: str | None = Field(None, description='请求 ID')
    data: T = Field(None,description="相应数据")