"""图内业务旁路消息信封（get_stream_writer → stream_mode=custom）。"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar('T')


class BusinessStreamMessageVo(BaseModel, Generic[T]):
    """
    图内推送业务旁路的基类 VO。

    Processor 只认 persist / push_sse：
    - push_sse → 统一 SSE 事件名 business（见 AgentSseEvent.BUSINESS）
    - persist → 落库 role=business，content 为 data JSON
    业务含义放在 data 内由前端自行识别，无需再扩事件枚举。
    """

    persist: bool = Field(default=False, description='是否落库')
    push_sse: bool = Field(default=True, description='是否推送前端 SSE')
    data: T = Field(description='业务载荷（结构由各业务自定）')
