"""精排专用 VO：入参带业务 id + 正文；出参原样回传 id + 分。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RerankDocumentVo(BaseModel):
    """精排输入：业务侧用 id 对齐，模型侧只用 text。"""

    id: str = Field(..., description='业务文档标识（命中 id），原样回传')
    text: str = Field(..., description='待打分正文')


class RerankResultVo(BaseModel):
    """精排输出：按相关性降序；用 id 回写原命中。"""

    id: str = Field(..., description='对应输入文档 id')
    score: float = Field(..., description='精排相关性分，越大越相关')
