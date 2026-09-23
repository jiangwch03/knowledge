"""Nacos 服务注册与发现。"""

from knowledge_common.nacos.client import NacosInstance, NacosNamingClient, get_nacos_client
from knowledge_common.nacos.lifecycle import nacos_deregister_current_app, nacos_register_current_app

__all__ = [
    'NacosInstance',
    'NacosNamingClient',
    'get_nacos_client',
    'nacos_register_current_app',
    'nacos_deregister_current_app',
]
