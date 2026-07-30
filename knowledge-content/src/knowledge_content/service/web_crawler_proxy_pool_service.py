"""爬虫代理池查询服务（sys_dict_data）"""

import json

from knowledge_common.mapper.dao.dict_dao import DictDataDao
from knowledge_common.utils.log_util import logger
from knowledge_content.enums.crawl_proxy_pool_dict_enum import CrawlProxyPoolDict
from knowledge_content.service.vo.proxy_pool_vo import ProxyPoolItemVo, ProxyPoolVo

_EMPTY_POOL_MESSAGE = (
    '当前环境未配置代理池（sys_dict_data 无 crawl_proxy_pool 条目）。'
    '请保持 proxy_config=null，优先使用 enable_stealth / simulate_user / magic / mean_delay 等反爬参数；'
    '禁止自行编造代理地址。'
)
_AVAILABLE_POOL_MESSAGE = (
    '已从系统字典加载代理池。高强度反爬且 trial 仍失败时，可使用返回的 proxies 配置 proxy_config；'
    '禁止自行编造未在列表中的代理地址。'
)


class WebCrawlerProxyPoolService:
    """查询运维在字典中维护的爬虫代理 IP 池"""

    @classmethod
    async def query_proxy_pool(cls) -> ProxyPoolVo:
        """
        查询 crawl_proxy_pool 字典下的可用代理节点

        :return: 代理池查询结果；无数据时 available=false
        """
        rows = await DictDataDao.query_dict_data_list(CrawlProxyPoolDict.DICT_TYPE)

        proxies: list[ProxyPoolItemVo] = []
        for row in rows:
            item = cls._parse_dict_row(row.dict_label, row.dict_value, row.remark)
            if item is not None:
                proxies.append(item)

        if not proxies:
            return ProxyPoolVo(
                available=False,
                pool_size=0,
                message=_EMPTY_POOL_MESSAGE,
                proxies=[],
            )

        return ProxyPoolVo(
            available=True,
            pool_size=len(proxies),
            message=_AVAILABLE_POOL_MESSAGE,
            proxies=proxies,
        )

    @staticmethod
    def _parse_dict_row(label: str | None, value: str | None, remark: str | None) -> ProxyPoolItemVo | None:
        """将 dict_value JSON 解析为 ProxyPoolItemVo"""
        if not value or not value.strip():
            logger.warning('[ProxyPool] 跳过空 dict_value: label={}', label)
            return None

        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            logger.warning('[ProxyPool] dict_value 非合法 JSON，跳过: label={}, remark={}', label, remark)
            return None

        if not isinstance(data, dict):
            logger.warning('[ProxyPool] dict_value 须为 JSON 对象，跳过: label={}', label)
            return None

        server = data.get('server') or data.get('url')
        if not server:
            logger.warning('[ProxyPool] dict_value 缺少 server/url，跳过: label={}', label)
            return None

        return ProxyPoolItemVo(
            label=(label or '').strip() or server,
            server=str(server).strip(),
            username=str(data.get('username') or ''),
            password=str(data.get('password') or ''),
        )
