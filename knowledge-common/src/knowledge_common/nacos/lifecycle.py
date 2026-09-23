"""FastAPI 生命周期：Nacos 注册 / 下线。"""

from __future__ import annotations

from knowledge_common.config.env import AppConfig, NacosConfig
from knowledge_common.nacos.client import get_nacos_client
from knowledge_common.utils.log_util import logger


async def nacos_register_current_app(*, service_name: str | None = None) -> None:
    """应用启动成功后注册到 Nacos（未启用则跳过）。"""
    if not NacosConfig.nacos_enabled:
        return
    name = (service_name or AppConfig.app_name or '').strip()
    if not name:
        logger.warning('[Nacos] skip register: empty service name')
        return
    try:
        await get_nacos_client().register(name)
    except Exception as e:
        # 注册失败默认不阻断启动，便于本地无 Nacos 时仅打日志
        if NacosConfig.nacos_fail_fast:
            raise
        logger.opt(exception=True).error('[Nacos] register failed (continue): {}', e)


async def nacos_deregister_current_app() -> None:
    if not NacosConfig.nacos_enabled:
        return
    try:
        await get_nacos_client().deregister()
    except Exception as e:
        logger.warning('[Nacos] deregister error: {}', e)
