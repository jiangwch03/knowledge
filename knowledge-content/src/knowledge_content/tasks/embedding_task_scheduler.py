"""
knowledge-content Embedding 任务定时兜底

- PENDING 长时间未消费 → 重新投递
- CHUNKING / EMBEDDING 停更（进程已死）→ 重投递断点续跑
- CHUNK_FAILED / EMBED_FAILED → 自动重置并重试（无需人工）
"""
from __future__ import annotations

from datetime import datetime

from knowledge_common.config.env import EmbeddingConfig
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger

from knowledge_content.mapper.dao.document_embedding_task_dao import KnowledgeDocumentEmbeddingTaskDao
from knowledge_content.mapper.do.document_embedding_task_do import KnowledgeDocumentEmbeddingTask
from knowledge_content.service.embedding_publish_service import EmbeddingPublishService
from knowledge_content.service.embedding_task_service import EmbeddingTaskService


class EmbeddingTaskScheduler:
    @classmethod
    async def run_fallback(cls) -> None:
        """Embedding 任务兜底：重投递 + 僵尸续跑 + 失败自动重试。"""
        # PENDING 超时未消费：重新投递 MQ
        await cls._repost_stale_pending()
        # CHUNKING / EMBEDDING 停更且抢到锁：进程已死，重投续跑
        await cls._repost_stuck_in_progress()
        # CHUNK_FAILED / EMBED_FAILED：自动重置并重试
        await cls._auto_retry_failed()

    @classmethod
    async def _repost_stale_pending(cls) -> None:
        """扫描长时间 PENDING 的任务，重新投递 MQ。"""
        before: datetime = KnowledgeDocumentEmbeddingTaskDao.stale_before(EmbeddingConfig.embedding_pending_repost_minutes)
        tasks: list[KnowledgeDocumentEmbeddingTask] = await KnowledgeDocumentEmbeddingTaskDao.list_stale_pending(before)
        if not tasks:
            return
        logger.info('[Embedding-scheduler] 扫描到 {} 个 stale PENDING 任务', len(tasks))
        for task in tasks:
            lock_key: str = LockKey.embedding_task_key(task.task_id)
            async with DistributedLock(lock_key, expire=60, timeout=0, renew=True) as acquired:
                if not acquired:
                    continue
                try:
                    await EmbeddingTaskService.republish_pending(task.task_id)
                    logger.info('[Embedding-scheduler] 重投递: task_id={}', task.task_id)
                except Exception as exc:
                    logger.exception('[Embedding-scheduler] 重投递失败: task_id={}, error={}', task.task_id, exc)

    @classmethod
    async def _repost_stuck_in_progress(cls) -> None:
        """扫描停更的 CHUNKING/EMBEDDING：抢到执行锁则重投续跑（抢不到说明仍在跑）。"""
        before: datetime = KnowledgeDocumentEmbeddingTaskDao.stale_before(EmbeddingConfig.embedding_task_timeout_minutes)
        tasks: list[KnowledgeDocumentEmbeddingTask] = await KnowledgeDocumentEmbeddingTaskDao.list_stuck_in_progress(before)
        if not tasks:
            return
        logger.info('[Embedding-scheduler] 扫描到 {} 个停更执行中任务', len(tasks))
        for task in tasks:
            lock_key: str = LockKey.embedding_task_key(task.task_id)
            try:
                # 持锁仅确认进程已死；消息放到锁外，避免消费端抢锁失败
                async with DistributedLock(lock_key, expire=30, timeout=0) as acquired:
                    if not acquired:
                        continue
                await EmbeddingTaskService.republish_stuck(task.task_id)
                logger.info('[Embedding-scheduler] 僵尸续跑重投递: task_id={}', task.task_id)
            except Exception as exc:
                logger.exception('[Embedding-scheduler] 僵尸续跑失败: task_id={}, error={}', task.task_id, exc)

    @classmethod
    async def _auto_retry_failed(cls) -> None:
        """扫描失败任务，自动重置到对应阶段并重投递（互斥由 Service 内 task 锁保证）。"""
        tasks: list[KnowledgeDocumentEmbeddingTask] = await KnowledgeDocumentEmbeddingTaskDao.list_failed_for_retry()
        if not tasks:
            return
        logger.info('[Embedding-scheduler] 扫描到 {} 个失败任务，准备自动重试', len(tasks))
        for task in tasks:
            try:
                await EmbeddingTaskService.auto_retry_failed(task.task_id)
                logger.info('[Embedding-scheduler] 失败自动重试: task_id={}', task.task_id)
            except Exception as exc:
                logger.exception('[Embedding-scheduler] 失败自动重试异常: task_id={}, error={}', task.task_id, exc)


async def embedding_task_fallback_job() -> None:
    """定时任务入口：Embedding 任务兜底。"""
    await EmbeddingTaskScheduler.run_fallback()


async def embedding_auto_publish_job() -> None:
    """临时：COMPLETED+canary → 发布（旧 prod → pending_delete）。正式发布 UI 上线后下线本 job。"""
    await EmbeddingPublishService.auto_promote_completed_canary()


async def embedding_pending_delete_cleanup_job() -> None:
    """临时：按批清理 pending_delete（Milvus 删向量 + MySQL 归档并物理删除）。正式链路可复用或下线。"""
    await EmbeddingPublishService.cleanup_pending_delete()
