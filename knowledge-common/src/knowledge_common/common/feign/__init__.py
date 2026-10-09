"""OpenFeign 风格跨服务调用：声明客户端、发现实例、统一解包。"""

from knowledge_common.common.feign.feign import Feign
from knowledge_common.common.feign.feign_client import FeignClient
from knowledge_common.common.feign.feign_page import FeignAckVo, FeignDataVo, FeignPageVo
from knowledge_common.common.feign.mapping import feign_client, get_mapping, post_mapping

__all__ = [
    'Feign',
    'FeignAckVo',
    'FeignClient',
    'FeignDataVo',
    'FeignPageVo',
    'feign_client',
    'get_mapping',
    'post_mapping',
]
