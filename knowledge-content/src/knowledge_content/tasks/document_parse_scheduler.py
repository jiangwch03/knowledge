"""
knowledge-content Stage2 / Stage3 / Stage4 定时任务

- Stage2 路径 A：每分钟扫描 LINK_FAILED + PENDING 任务，重新申请上传链接
- Stage2 路径 B：每分钟扫描 UPLOAD_FAILED 分段，复用链接重试或标记超时
- Stage3：每分钟扫描 PARSING 任务，轮询 MinerU 解析结果
- Stage4：每 5 分钟扫描 CONVERT_FAILED 记录 + COMPLETED 未落库记录，重新发布合并消息
"""
from __future__ import annotations

from knowledge_common.common.transactional import get_current_session, with_session
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger

from knowledge_content.enums.document_upload_status_enum import DocumentUploadStatus
from knowledge_content.enums.mineru_parse_detail_state_enum import MineruParseDetailState
from knowledge_content.enums.mineru_parse_task_status_enum import MineruParseTaskStatus
from knowledge_content.mapper.dao.mineru_parse_detail_task_dao import (
    KnowledgeMineruParseDetailTaskDao,
)
from knowledge_content.mapper.dao.mineru_parse_task_dao import KnowledgeMineruParseTaskDao
from knowledge_content.mapper.dao.upload_task_dao import KnowledgeUploadTaskDao
from knowledge_content.mapper.do.parse_detail_task_do import KnowledgeMineruParseDetailTask
from knowledge_content.service.document_upload_parse_service import DocumentUploadParseService


class DocumentParseScheduler:
    """
    文档解析定时任务调度器
    """

    @classmethod
    async def stage2_path_a_link_failed(cls) -> None:
        """Stage2 路径 A：重新申请上传链接 + PENDING 超时兜底"""
        tasks = await KnowledgeMineruParseTaskDao.get_tasks_by_status(
            MineruParseTaskStatus.LINK_FAILED.value
        )
        logger.info(f'[Stage2-A] 扫描到 {len(tasks)} 个 LINK_FAILED 任务')
        for task in tasks:
            try:
                # 分布式锁：基于 task_id，与删除接口互斥
                lock_key = LockKey.upload_task_key(task.task_id)
                async with DistributedLock(lock_key, expire=120, timeout=0) as acquired:
                    if not acquired:
                        logger.info(
                            f'[Stage2-A] 上传任务正在处理中，跳过: parse_task_id={task.parse_task_id}, task_id={task.task_id}')
                        continue

                    await DocumentUploadParseService.process_pending_task(task.parse_task_id)
            except Exception as e:
                logger.error(f'[Stage2-A] 处理 LINK_FAILED 失败: parse_task_id={task.parse_task_id}, error={e}')

        # PENDING 兜底：消息流消费失败时，由定时任务接管处理
        pending_tasks = await KnowledgeMineruParseTaskDao.get_tasks_by_status(
            MineruParseTaskStatus.PENDING.value,
        )
        logger.info(f'[Stage2-A] 扫描到 {len(pending_tasks)} 个 PENDING 任务')
        for task in pending_tasks:
            try:
                # 分布式锁：基于 task_id，与删除接口互斥
                lock_key = LockKey.upload_task_key(task.task_id)
                async with DistributedLock(lock_key, expire=120, timeout=0) as acquired:
                    if not acquired:
                        logger.info(
                            f'[Stage2-A] 上传任务正在处理中，跳过: parse_task_id={task.parse_task_id}, task_id={task.task_id}')
                        continue

                    await DocumentUploadParseService.process_pending_task(task.parse_task_id)
            except Exception as e:
                logger.error(f'[Stage2-A] 处理 PENDING 兜底失败: parse_task_id={task.parse_task_id}, error={e}')

    @classmethod
    async def stage2_path_b_upload_failed(cls) -> None:
        """Stage2 路径 B：复用链接重试上传或标记超时"""
        details: list[KnowledgeMineruParseDetailTask] = await KnowledgeMineruParseDetailTaskDao.get_details_by_state(
            MineruParseDetailState.UPLOAD_FAILED.value
        )
        logger.info(f'[Stage2-B] 扫描到 {len(details)} 个 UPLOAD_FAILED 分段')

        # 按 parse_task_id 分组
        batch_groups: dict[int, list[KnowledgeMineruParseDetailTask]] = {}
        for detail in details:
            batch_groups.setdefault(detail.parse_task_id, []).append(detail)

        for parse_task_id, batch_details in batch_groups.items():
            # 按batch_id处理一个文档中上传失败的分段
            try:
                # 先查询任务获取 task_id
                task = await KnowledgeMineruParseTaskDao.get_task_by_id(parse_task_id)
                if not task:
                    logger.info(f'[Stage2-B] 解析任务不存在，跳过: parse_task_id={parse_task_id}')
                    continue

                # 分布式锁：基于 task_id，与删除接口互斥
                lock_key = LockKey.upload_task_key(task.task_id)
                async with DistributedLock(lock_key, expire=120, timeout=0) as acquired:
                    if not acquired:
                        logger.info(
                            f'[Stage2-B] 上传任务正在处理中，跳过: parse_task_id={parse_task_id}, task_id={task.task_id}')
                        continue

                    DocumentUploadParseService.stage2_path_b_upload_failed(parse_task_id, batch_details)
            except Exception as e:
                logger.error(f'[Stage2-B] 处理分段失败: parse_task_id={parse_task_id}, error={e}')

    @classmethod
    async def stage3_poll_results(cls) -> None:
        """Stage3：轮询 MinerU 解析结果"""
        tasks = await KnowledgeMineruParseTaskDao.get_tasks_by_status(
            MineruParseTaskStatus.PARSING.value
        )
        logger.info(f'[Stage3] 扫描到 {len(tasks)} 个 PARSING 任务')

        for task in tasks:
            if not task.batch_id:
                continue
            try:
                # 分布式锁：基于 task_id，与删除接口互斥
                lock_key = LockKey.upload_task_key(task.task_id)
                need_publish = False
                async with DistributedLock(lock_key, expire=120, timeout=0) as acquired:
                    if not acquired:
                        logger.info(
                            f'[Stage3] 上传任务正在处理中，跳过: parse_task_id={task.parse_task_id}, task_id={task.task_id}')
                        continue

                    need_publish = await DocumentUploadParseService.poll_parse_results(
                        task.parse_task_id, task.task_id, task.batch_id
                    )
                if need_publish:
                    await DocumentUploadParseService.publish_md_pending(task.task_id)
                    logger.info(f'[Stage3] 发布 md pending: task_id={task.task_id}')
            except Exception as e:
                logger.error(f'[Stage3] 轮询失败: parse_task_id={task.parse_task_id}, error={e}')

    @classmethod
    async def stage4_retry_convert_failed(cls) -> None:
        """Stage4：重新触发 md 合并（CONVERT_FAILED + COMPLETED 兜底）"""
        records = await KnowledgeUploadTaskDao.get_tasks_by_statuses(
            [DocumentUploadStatus.CONVERT_FAILED.value, DocumentUploadStatus.COMPLETED.value]
        )
        if not records:
            return
        logger.info(f'[Stage4] 扫描到 {len(records)} 个兜底记录')

        for record in records:

            lock_key = LockKey.upload_task_key(record.task_id)
            async with DistributedLock(lock_key, expire=180, timeout=0) as acquired:
                if not acquired:
                    logger.info(f'[Stage4] 上传任务正在处理中，跳过: task_id={record.task_id}')
                    continue
                try:
                    await DocumentUploadParseService.process_md_pending(record.task_id)
                except Exception as e:
                    logger.error(f'[Stage4] 处理失败: task_id={record.task_id}, error={e}')
                    await KnowledgeUploadTaskDao.update_status(
                        record.task_id,
                        DocumentUploadStatus.CONVERT_FAILED.value,
                        error_code='STAGE4_ERROR',
                        error_message=str(e),
                    )
                    db = get_current_session()
                    await db.commit()


# APScheduler 可调用的顶层异步函数


@with_session
async def stage2_path_a_job() -> None:
    """Stage2 路径 A 定时任务入口"""
    await DocumentParseScheduler.stage2_path_a_link_failed()


@with_session
async def stage2_path_b_job() -> None:
    """Stage2 路径 B 定时任务入口"""
    await DocumentParseScheduler.stage2_path_b_upload_failed()


@with_session
async def stage3_poll_job() -> None:
    """Stage3 定时任务入口"""
    await DocumentParseScheduler.stage3_poll_results()


@with_session
async def stage4_retry_job() -> None:
    """Stage4 定时任务入口"""
    await DocumentParseScheduler.stage4_retry_convert_failed()
