from datetime import datetime
from typing import Any, Literal

from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.vo.base_vo import BaseVo
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class EvalDatasetCreateVo(BaseVo):
    """创建测评集。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str = Field(..., min_length=1, max_length=128, description='测评集名称')
    doc_id: int = Field(..., description='绑定文档 ID')
    description: str | None = Field(default=None, max_length=500, description='描述')
    question_count: int = Field(..., ge=50, le=200, description='要生成的题目数量，至少 50')


class EvalDatasetModel(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    dataset_id: int | None = Field(default=None, description='测评集ID')
    name: str | None = Field(default=None, description='名称')
    doc_id: int | None = Field(default=None, description='文档ID')
    description: str | None = Field(default=None, description='描述')
    status: str | None = Field(
        default=None,
        description='INIT/MATERIAL_DONE/SIMPLE_DONE/MULTI_DONE/READY，失败为对应 _FAILED',
    )
    item_count: int | None = Field(default=None, description='题目数')
    question_count: int | None = Field(default=None, description='请求生成的题目数量')
    user_id: int | None = Field(default=None)
    dept_id: int | None = Field(default=None)
    create_by: str | None = Field(default=None)
    create_time: datetime | None = Field(default=None)
    update_by: str | None = Field(default=None)
    update_time: datetime | None = Field(default=None)
    remark: str | None = Field(default=None)


class EvalDatasetPageQueryModel(EvalDatasetModel, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EvalDatasetItemModel(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    item_id: int | None = Field(default=None)
    dataset_id: int | None = Field(default=None)
    question: str | None = Field(default=None)
    ground_truth: str | None = Field(default=None)
    reference_excerpts: str | None = Field(default=None)
    used_chunk_ids: str | None = Field(default=None)
    keypoints: str | None = Field(default=None)
    difficulty: str | None = Field(default=None)
    sort_order: int | None = Field(default=None)
    enabled: int | None = Field(default=None)
    create_by: str | None = Field(default=None)
    create_time: datetime | None = Field(default=None)
    update_by: str | None = Field(default=None)
    update_time: datetime | None = Field(default=None)


class EvalDatasetItemPageQueryModel(BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    dataset_id: int | None = Field(default=None, description='测评集ID')
    question: str | None = Field(default=None, description='问题，模糊匹配')
    difficulty: str | None = Field(
        default=None, description='题目类型 simple/multi_hop/comprehensive/vague/adversarial'
    )
    enabled: int | None = Field(default=None, description='1 计入测评，0 排除')


class EvalDatasetItemUpdateVo(BaseVo):
    """出题完成后只改问题和标准答案，原文摘录不改。也可排除本题不参与测评。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    question: str | None = Field(default=None, description='问题')
    ground_truth: str | None = Field(default=None, description='标准答案')
    enabled: int | None = Field(default=None, description='1 跑测评时计入这道题，0 人工排除、不参与测评，题目仍保留')


class EvalDatasetDetailVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    dataset: EvalDatasetModel
    items: list[EvalDatasetItemModel] = Field(default_factory=list)


class EvalTaskCreateVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    dataset_id: int = Field(..., description='测评集ID')
    embedding_task_id: int = Field(..., description='COMPLETED canary embedding 任务ID')
    name: str = Field(..., min_length=1, max_length=128, description='任务名称')


class EvalTaskSwapDatasetVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    dataset_id: int = Field(..., description='新测评集ID')


class EvalTaskModel(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    eval_task_id: int | None = Field(default=None)
    name: str | None = Field(default=None)
    embedding_task_id: int | None = Field(default=None)
    doc_id: int | None = Field(default=None)
    dataset_id: int | None = Field(default=None)
    status: str | None = Field(default=None, description='OPEN/ARCHIVED')
    publish_time: datetime | None = Field(default=None)
    user_id: int | None = Field(default=None)
    dept_id: int | None = Field(default=None)
    create_by: str | None = Field(default=None)
    create_time: datetime | None = Field(default=None)
    update_by: str | None = Field(default=None)
    update_time: datetime | None = Field(default=None)
    remark: str | None = Field(default=None)


class EvalTaskListItemModel(EvalTaskModel):
    """列表行：在任务字段外补文档标题、测评集名称、向量化切分策略名。"""

    doc_title: str | None = Field(default=None, description='文档标题')
    dataset_name: str | None = Field(default=None, description='测评集名称')
    embedding_split_label: str | None = Field(default=None, description='向量化任务切分策略名')


class EvalDatasetNameVo(BaseModel):
    """测评集 ID 与名称，只给列表补展示。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    dataset_id: int
    name: str = ''


class EvalTaskPageQueryModel(EvalTaskModel, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class EvalRunModel(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    run_id: int | None = Field(default=None)
    eval_task_id: int | None = Field(default=None)
    dataset_id: int | None = Field(default=None)
    embedding_task_id: int | None = Field(default=None)
    release_tag: str | None = Field(default=None)
    status: str | None = Field(default=None)
    dataset_snapshot: str | None = Field(default=None)
    summary_metrics: str | None = Field(default=None)
    report_text: str | None = Field(default=None)
    embedding_model_code: str | None = Field(default=None)
    llm_version: str | None = Field(default=None)
    judge_model_code: str | None = Field(default=None)
    error_message: str | None = Field(default=None)
    started_at: datetime | None = Field(default=None)
    finished_at: datetime | None = Field(default=None)
    create_by: str | None = Field(default=None)
    create_time: datetime | None = Field(default=None)


class EvalRunItemModel(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    run_item_id: int | None = Field(default=None)
    run_id: int | None = Field(default=None)
    dataset_item_id: int | None = Field(default=None)
    question: str | None = Field(default=None)
    ground_truth: str | None = Field(default=None)
    reference_excerpts: str | None = Field(default=None)
    contexts: str | None = Field(default=None)
    answer: str | None = Field(default=None)
    metrics: str | None = Field(default=None)
    sort_order: int | None = Field(default=None)


class EvalItemScoreVo(BaseModel):
    """一道题的四项分数。没有分的指标留空。"""

    model_config = ConfigDict(populate_by_name=True)

    context_recall: float | None = None
    context_precision: float | None = None
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    note: str | None = None


class EvalRunSummaryVo(BaseModel):
    """一次执行的进度和四项均分。跑完一批就更新，全部完成后再定稿。"""

    model_config = ConfigDict(populate_by_name=True)

    item_total: int = 0
    item_done: int = 0
    context_recall: float | None = None
    context_precision: float | None = None
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    note: str | None = None


class EvalRunReportVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    run: EvalRunModel
    items: list[EvalRunItemModel] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class EvalRunPageQueryModel(BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    eval_task_id: int | None = Field(default=None)


class GeneratedDatasetItemVo(BaseModel):
    """生成结果。difficulty 是题目类型：simple / multi_hop / comprehensive / vague / adversarial。"""

    model_config = ConfigDict(populate_by_name=True)

    question: str
    ground_truth: str = ''
    difficulty: str = ''
    reference_excerpts: list[str] = Field(default_factory=list)
    used_chunk_ids: list[str] = Field(default_factory=list)
    keypoints: list[str] = Field(default_factory=list)


class EvalDatasetSnapshotItemVo(BaseModel):
    """跑测评时写入 run.dataset_snapshot 的题目快照（admin 内部）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    item_id: int | None = None
    question: str = ''
    ground_truth: str = ''
    reference_excerpts: str | None = None
    difficulty: str | None = None
    sort_order: int | None = None


class EvalRunPendingQuestionVo(BaseModel):
    """续跑或新跑时还没入库的一道题。sort_order 是这次执行里的原顺序。"""

    model_config = ConfigDict(populate_by_name=True)

    sort_order: int
    snap: EvalDatasetSnapshotItemVo


class EvalRunLaunchVo(BaseModel):
    """交给后台的一次执行计划。不直接返回给页面。"""

    model_config = ConfigDict(populate_by_name=True)

    run: EvalRunModel
    message: str
    run_id: int
    embedding_task_id: int
    update_by: str
    user_id: int
    item_total: int
    resume: bool = False
    prior_scores: list[EvalItemScoreVo] = Field(default_factory=list)
    pending: list[EvalRunPendingQuestionVo] = Field(default_factory=list)


EvalTaskStatus = Literal['OPEN', 'ARCHIVED']
EvalRunStatus = Literal['PENDING', 'RUNNING', 'SUCCESS', 'FAILED']
