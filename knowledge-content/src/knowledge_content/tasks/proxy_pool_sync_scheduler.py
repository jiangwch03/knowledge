"""
外部代理池 → 系统字典：拉取 / 清理定时任务

- 拉取：只新增字典中尚不存在的代理（默认每 30 秒）
- 清理：只删除探测不通的节点（默认每 1 分钟）
"""

from knowledge_common.utils.log_util import logger
from knowledge_content.service.proxy_pool_dict_sync_service import ProxyPoolDictSyncService


async def sync_proxy_pool_fetch_job(*args, **kwargs) -> None:
    """
    拉取外部代理池新增节点到 crawl_proxy_pool 字典

    invoke_target: knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_fetch_job
    """
    try:
        result = await ProxyPoolDictSyncService.fetch_from_api()
        logger.info('[ProxyPool] 拉取任务结束: {}', result)
    except Exception as e:
        logger.exception('[ProxyPool] 拉取任务失败: {}', e)
        raise


async def sync_proxy_pool_cleanup_job(*args, **kwargs) -> None:
    """
    清理字典中不通的代理节点

    invoke_target: knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_cleanup_job
    """
    try:
        result = await ProxyPoolDictSyncService.cleanup_dead()
        logger.info('[ProxyPool] 清理任务结束: {}', result)
    except Exception as e:
        logger.exception('[ProxyPool] 清理任务失败: {}', e)
        raise
