"""Nacos 服务注册与发现。

能力对齐 Spring Cloud Alibaba Nacos Discovery：
- 注册 / 下线 + SDK 心跳（ephemeral）
- 本机注册 IP 进程内缓存
- 服务实例本地缓存 + subscribe 推送
"""

from knowledge_common.nacos.client import NacosInstance, NacosNamingClient, get_nacos_client
from knowledge_common.nacos.lifecycle import nacos_deregister_current_app, nacos_register_current_app

__all__ = [
    'NacosInstance',
    'NacosNamingClient',
    'get_nacos_client',
    'nacos_register_current_app',
    'nacos_deregister_current_app',
]
