"""query_proxy_pool 工具与代理池服务测试"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge_content.agents.tools.query_proxy_pool import query_proxy_pool
from knowledge_content.service.web_crawler_proxy_pool_service import WebCrawlerProxyPoolService


class _FakeDictRow:
    def __init__(self, label: str, value: str, remark: str = ''):
        self.dict_label = label
        self.dict_value = value
        self.remark = remark


@pytest.mark.asyncio
async def test_query_proxy_pool_empty():
    with patch(
        'knowledge_content.service.web_crawler_proxy_pool_service.DictDataDao.query_dict_data_list',
        new_callable=AsyncMock,
        return_value=[],
    ):
        result = await WebCrawlerProxyPoolService.query_proxy_pool()

    assert result.available is False
    assert result.pool_size == 0
    assert result.proxies == []
    assert 'proxy_config=null' in result.message


@pytest.mark.asyncio
async def test_query_proxy_pool_with_nodes():
    rows = [
        _FakeDictRow('节点1', '{"server":"http://127.0.0.1:7890","username":"u","password":"p"}'),
    ]
    with patch(
        'knowledge_content.service.web_crawler_proxy_pool_service.DictDataDao.query_dict_data_list',
        new_callable=AsyncMock,
        return_value=rows,
    ):
        result = await WebCrawlerProxyPoolService.query_proxy_pool()

    assert result.available is True
    assert result.pool_size == 1
    assert result.proxies[0].server == 'http://127.0.0.1:7890'
    assert result.proxies[0].username == 'u'


@pytest.mark.asyncio
async def test_query_proxy_pool_tool_returns_json():
    with patch(
        'knowledge_content.agents.tools.query_proxy_pool.WebCrawlerProxyPoolService.query_proxy_pool',
        new_callable=AsyncMock,
    ) as mock_service:
        from knowledge_content.service.vo.proxy_pool_vo import ProxyPoolVo

        mock_service.return_value = ProxyPoolVo(
            available=False,
            pool_size=0,
            message='无代理池',
            proxies=[],
        )
        raw = await query_proxy_pool.ainvoke({})

    assert 'available' in raw
    assert 'false' in raw.lower()
