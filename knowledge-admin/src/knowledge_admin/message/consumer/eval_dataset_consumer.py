"""测评集生成消费者。"""

from __future__ import annotations

from typing import Any

from knowledge_admin.service.eval_dataset_generate_service import (
    EvalDatasetGenerateService,
    get_eval_dataset_generate_semaphore,
)
from knowledge_admin.service.vo.eval_dataset_message_vo import EvalDatasetPending
from knowledge_common.config.env import StreamTopicConfig
from knowledge_common.message_stream import Message, consumer
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger


@consumer(
    topic=StreamTopicConfig.eval_dataset_pending,
    group_id='knowledge_admin',
    pre_ack=True,
)
async def handle_eval_dataset_pending(msg: Message) -> None:
    value: Any = msg.value or {}
    payload = EvalDatasetPending.model_validate(value)
    dataset_id = payload.dataset_id
    lock_key = LockKey.eval_dataset_key(dataset_id)
    async with DistributedLock(lock_key, expire=180, timeout=0, renew=True) as acquired:
        if not acquired:
            logger.info(
                '[EvalDataset-consumer] 测评集正在出题，跳过重复消息，避免重复出题 dataset_id={}',
                dataset_id,
            )
            return
        semaphore = await get_eval_dataset_generate_semaphore()
        async with semaphore:
            logger.info('[EvalDataset-consumer] 开始按文档为测评集出题 dataset_id={}', dataset_id)
            await EvalDatasetGenerateService.run(dataset_id)
