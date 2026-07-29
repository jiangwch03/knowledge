"""
models.dev Profile 本地索引同步定时任务

每日拉取 https://models.dev/api.json，刷新本地 profile 索引，供管理端「获取 Profile」按 model_code 查询。
"""

from knowledge_admin.service.models_dev_profile_service import ModelsDevProfileService
from knowledge_common.utils.log_util import logger


async def sync_models_dev_profiles(*args, **kwargs) -> None:
    """
    同步 models.dev 模型 Profile 索引

    invoke_target: knowledge_admin.tasks.models_dev_profile_sync.sync_models_dev_profiles
    """
    try:
        meta = await ModelsDevProfileService.sync_from_remote()
        logger.info(
            f'[models.dev] 定时同步成功: model_count={meta.get("model_count")}, synced_at={meta.get("synced_at")}'
        )
    except Exception as e:
        logger.exception(f'[models.dev] 定时同步失败: {e}')
        raise
