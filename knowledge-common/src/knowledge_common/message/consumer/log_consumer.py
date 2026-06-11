"""
日志聚合消费者（common 集中维护，admin / rag 自动复用）

通过 @consumer 装饰器声明 4 个消费函数（admin/rag × login/operation），
由 MessageStreamService 框架自动拉起后台消费协程。
业务侧零代码复制，admin / rag 任一进程启动时都会 import 该文件并触发装饰器注册。

topic 命名：log:{event_type}:{app_name}
group_id 命名：log_writer:{app_name}
"""
from __future__ import annotations

from typing import Awaitable, Callable

from knowledge_common.config.env import AppConfig
from knowledge_common.dao.log_dao import LoginLogDao, OperationLogDao
from knowledge_common.entity.vo.log_vo import LogininforModel, OperLogModel
from knowledge_common.message_stream import Message, consumer
from knowledge_common.service.log_service import LogDedupHelper
from knowledge_common.config.database import AsyncSessionLocal

TOPIC_OPERATION = f'log:operation:{AppConfig.app_name}'
TOPIC_LOGIN = f'log:login:{AppConfig.app_name}'
GROUP_ID = f'log_writer:{AppConfig.app_name}'

async def _persist_log(
    msg: Message,
    default_app: str,
    model_cls: type,
    dao_method: Callable[..., Awaitable],
) -> None:
    """通用日志落库：去重 → 建模 → 持久化"""
    event_id = msg.headers.get('event_id')
    app_name = msg.headers.get('app_name', default_app)
    async with LogDedupHelper.acquire(event_id, app_name) as ok:
        if not ok:
            return
        async with AsyncSessionLocal() as session:
            log_entry = model_cls(**msg.value)
            await dao_method(session, log_entry)
            await session.commit()

@consumer(topic = TOPIC_LOGIN, group_id = GROUP_ID)
async def handle_login_log(msg: Message) -> None:
    await _persist_log(msg, AppConfig.APP_NAME, LogininforModel, LoginLogDao.add_login_log_dao)


@consumer(topic =TOPIC_OPERATION, group_id = GROUP_ID)
async def handle_operation_log(msg: Message) -> None:
    await _persist_log(msg, AppConfig.APP_NAME, OperLogModel, OperationLogDao.add_operation_log_dao)

__all__ = [
    'handle_login_log',
    'handle_operation_log',
]
