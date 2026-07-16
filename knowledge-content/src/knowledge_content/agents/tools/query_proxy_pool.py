"""
网页爬取 Agent 工具 - 查询系统代理 IP 池

从 sys_dict_data（dict_type=crawl_proxy_pool）读取运维配置的代理节点。
LLM 不得自行编造代理地址，高强度反爬需代理时必须先调用本工具。
"""

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.vo.proxy_pool_vo import ProxyPoolVo
from knowledge_content.service.web_crawler_proxy_pool_service import WebCrawlerProxyPoolService


@tool
async def query_proxy_pool() -> str:
    """
    查询系统已配置的爬虫代理 IP 池（字典 crawl_proxy_pool）。

    无入参。返回 JSON 字符串，字段包括：
    - available: 是否有可用代理（false 表示当前未配置代理池）
    - pool_size: 节点数量
    - message: 使用说明（无池时须保持 proxy_config=null）
    - proxies: 节点列表，每项含 label、server、username、password

    使用规则：
    - 配置策略前若考虑代理，必须先调用本工具
    - available=false 时禁止输出 proxy_config，改用反爬参数
    - 仅可使用返回列表中的 server，禁止虚构代理
    """
    try:
        result: ProxyPoolVo = await WebCrawlerProxyPoolService.query_proxy_pool()
        return result.model_dump_json(ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[Planning] query_proxy_pool 异常: {}', err)
        fallback = ProxyPoolVo(
            available=False,
            pool_size=0,
            message=f'查询代理池失败: {err}。请保持 proxy_config=null，禁止编造代理地址。',
            proxies=[],
        )
        return fallback.model_dump_json(ensure_ascii=False)
