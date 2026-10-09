"""出题圈资料的内部结构。不对外接口。"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuestionQuotaVo(BaseModel):
    """按 4:2:2:1:1 拆开的题数。"""

    simple: int = 0
    multi_hop: int = 0
    comprehensive: int = 0
    vague: int = 0
    adversarial: int = 0


class EvalPageVo(BaseModel):
    """爬取文档里的一页原文。index 是这一批里的顺序。"""

    index: int
    source_url: str = ''
    text: str = ''
    file_id: int = 0
    doc_name: str = ''


class EvalMaterialDocVo(BaseModel):
    """送去出题的一份材料。"""

    page_content: str
    file_id: int | None = None
    doc_name: str = ''
    source_url: str = ''
    title: str = ''


class GenerationMaterialPlanVo(BaseModel):
    """圈完的材料。大于 20 时三份材料不同，不超过 20 时三份都是全部页。"""

    separate_ragas_calls: bool
    simple_docs: list[EvalMaterialDocVo] = Field(default_factory=list)
    multi_hop_docs: list[EvalMaterialDocVo] = Field(default_factory=list)
    custom_docs: list[EvalMaterialDocVo] = Field(default_factory=list)
    quota: QuestionQuotaVo


class EvalDatasetMaterialRecordVo(BaseModel):
    """圈资料落库的内容。后面的阶段只读这份，不再下载。"""

    plan: GenerationMaterialPlanVo
    cached_object_keys: list[str] = Field(default_factory=list)


class RagasCallVo(BaseModel):
    """一次 RAGAS 出题。kind=all 时不传 query_distribution。"""

    docs: list[EvalMaterialDocVo]
    testset_size: int
    kind: Literal['single', 'multi']


class CustomQuestionDraftVo(BaseModel):
    """模型写出的一道自写题。"""

    question: str = ''
    ground_truth: str = ''
    excerpts: list[str] = Field(default_factory=list)


class CustomQuestionBatchVo(BaseModel):
    """一次写出的模糊、对抗、综合题。"""

    comprehensive: list[CustomQuestionDraftVo] = Field(default_factory=list)
    vague: list[CustomQuestionDraftVo] = Field(default_factory=list)
    adversarial: list[CustomQuestionDraftVo] = Field(default_factory=list)
