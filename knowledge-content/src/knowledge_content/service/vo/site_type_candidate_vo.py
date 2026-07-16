"""站点类型候选 VO（探针④打分层输出）"""

from pydantic import BaseModel, Field


class SiteTypeCandidateVo(BaseModel):
    """
    对齐 prompts.yaml「三、站点类型识别说明」的候选类型及置信度。

    探针只打分与列依据，最终 site_type 由 Planning Agent 决策。
    """

    site_type: str  # 候选站点类型（对齐 prompts.yaml 八种类型）
    score: float = 0.0  # 综合置信分，越高越匹配
    signals: list[str] = Field(default_factory=list)  # 打分依据（可解释性信号）
