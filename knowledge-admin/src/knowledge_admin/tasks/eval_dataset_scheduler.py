"""测评集生成定时兜底：未完成的进度超时重投，失败状态重试。"""

from knowledge_admin.service.eval_dataset_service import EvalDatasetService


async def eval_dataset_fallback_job() -> None:
    """invoke_target: knowledge_admin.tasks.eval_dataset_scheduler.eval_dataset_fallback_job"""
    await EvalDatasetService.repost_stale()
    await EvalDatasetService.retry_failed()
