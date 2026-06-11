"""
定时任务广播订阅者（common 集中维护，admin / rag 自动复用）

通过 @subscriber 装饰器声明，由 BroadcastService 框架自动注册和启动监听。
业务方零代码复制，admin / rag 任一进程启动时都会 import 该文件并触发装饰器注册。

channel: scheduler:global:sync
"""
from __future__ import annotations

from knowledge_common.broadcast import BroadcastMessage, subscriber
from knowledge_common.config.get_scheduler import SchedulerUtil
from knowledge_common.utils.log_util import logger


@subscriber(channel='scheduler:global:sync')
async def on_global_sync_message(msg: BroadcastMessage) -> None:
    """
    全局广播消息处理 handler

    仅 Leader 才会响应，app_scope 不匹配的消息会被丢弃。

    :param msg: 广播消息（payload 已自动反序列化为 dict）
    """
    if not SchedulerUtil._is_leader:
        return

    data = msg.payload if isinstance(msg.payload, dict) else {}
    msg_app_scope = data.get('app_scope')

    # 如果广播指定了 app_scope，且不是本项目的，跳过
    if msg_app_scope and msg_app_scope != SchedulerUtil._app_scope:
        return

    action = data.get('action', 'sync')
    if action == 'execute_once':
        job_id = data.get('job_id')
        if job_id:
            await SchedulerUtil._execute_job_once_from_broadcast(job_id)
        return

    await SchedulerUtil.request_scheduler_sync()


__all__ = ['on_global_sync_message']
