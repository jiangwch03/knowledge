from enum import Enum


class EvalDatasetStatus(str, Enum):
    """测评集状态。创建后按这个顺序走，不再另放一层草稿/出题中。"""

    INIT = 'INIT'  # 初始化
    MATERIAL_DONE = 'MATERIAL_DONE'  # 圈资料完成
    SIMPLE_DONE = 'SIMPLE_DONE'  # 简单题完成
    MULTI_DONE = 'MULTI_DONE'  # 多跳题完成
    CUSTOM_DONE = 'CUSTOM_DONE'  # 自写题写完，对外改成可测评
    READY = 'READY'  # 可测评
    MATERIAL_FAILED = 'MATERIAL_FAILED'
    SIMPLE_FAILED = 'SIMPLE_FAILED'
    MULTI_FAILED = 'MULTI_FAILED'
    CUSTOM_FAILED = 'CUSTOM_FAILED'


_STAGE_ORDER = ('MATERIAL', 'SIMPLE', 'MULTI', 'CUSTOM')

IN_PROGRESS_STATUSES = (
    EvalDatasetStatus.INIT.value,
    EvalDatasetStatus.MATERIAL_DONE.value,
    EvalDatasetStatus.SIMPLE_DONE.value,
    EvalDatasetStatus.MULTI_DONE.value,
)
FAILED_STATUSES = (
    EvalDatasetStatus.MATERIAL_FAILED.value,
    EvalDatasetStatus.SIMPLE_FAILED.value,
    EvalDatasetStatus.MULTI_FAILED.value,
    EvalDatasetStatus.CUSTOM_FAILED.value,
)
RUNNABLE_STATUSES = IN_PROGRESS_STATUSES + FAILED_STATUSES


def stage_finished(stage: str | None, name: str) -> bool:
    """name 这一阶段是否已经成功写库。失败只说明它前面的阶段完成了。"""
    current = _stage_name(stage)
    outcome = _stage_outcome(stage)
    if current is None or outcome is None or name not in _STAGE_ORDER:
        return False
    if outcome == 'DONE':
        return _STAGE_ORDER.index(name) <= _STAGE_ORDER.index(current)
    return _STAGE_ORDER.index(name) < _STAGE_ORDER.index(current)


def pending_stage(stage: str | None) -> str | None:
    """下一个还没完成的阶段。四个都完成时返回 None。"""
    for name in _STAGE_ORDER:
        if not stage_finished(stage, name):
            return name
    return None


def failed_stage(name: str) -> EvalDatasetStatus:
    """把阶段名收成失败状态。"""
    return EvalDatasetStatus(f'{name}_FAILED')


def _stage_name(stage: str | None) -> str | None:
    if not stage or '_' not in stage:
        return None
    name = stage.rsplit('_', 1)[0]
    if name not in _STAGE_ORDER:
        return None
    return name


def _stage_outcome(stage: str | None) -> str | None:
    if not stage or '_' not in stage:
        return None
    outcome = stage.rsplit('_', 1)[1]
    if outcome not in ('DONE', 'FAILED'):
        return None
    return outcome
