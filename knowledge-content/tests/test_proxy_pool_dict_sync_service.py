"""ProxyPoolDictSyncService 拉取 / 清理测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_content.service.proxy_pool_dict_sync_service import (
    ProxyPoolDictSyncService,
    _DictProxyNode,
)


class _FakeDictRow:
    def __init__(
        self,
        label: str,
        value: str,
        remark: str = '',
        dict_code: int = 1,
        dict_sort: int = 1,
    ):
        self.dict_label = label
        self.dict_value = value
        self.remark = remark
        self.dict_code = dict_code
        self.dict_sort = dict_sort


def _enable_cfg(cfg) -> None:
    cfg.proxy_pool_sync_enabled = True
    cfg.proxy_pool_api_base_url = 'http://127.0.0.1:5010'
    cfg.proxy_pool_sync_limit = 50
    cfg.proxy_pool_request_timeout = 15
    cfg.proxy_pool_verify_enabled = True
    cfg.proxy_pool_verify_url = 'https://www.baidu.com'
    cfg.proxy_pool_verify_timeout = 8
    cfg.proxy_pool_verify_concurrency = 20
    cfg.proxy_pool_delete_dead = True


def test_map_api_payload_builds_compact_dict_rows():
    raw = [
        {'proxy': '1.2.3.4:8080', 'https': False, 'region': 'CN', 'source': 'scdn', 'last_status': True},
        {'proxy': '1.2.3.4:8080', 'https': False, 'region': 'CN', 'source': 'scdn', 'last_status': True},
        {'proxy': '5.6.7.8:443', 'https': True, 'region': 'US', 'source': 'goodips', 'last_status': True},
        {'proxy': '9.9.9.9:80', 'https': False, 'last_status': False},
        {'proxy': 'bad', 'https': False},
    ]
    candidates = ProxyPoolDictSyncService._map_api_payload(raw, limit=50)

    assert len(candidates) == 2
    assert candidates[0].proxy == '1.2.3.4:8080'
    assert candidates[0].row.dict_value == '{"server":"http://1.2.3.4:8080"}'
    assert candidates[1].row.dict_value == '{"server":"https://5.6.7.8:443"}'


def test_map_api_payload_respects_limit():
    raw = [{'proxy': f'1.1.1.{i}:80', 'https': False, 'last_status': True} for i in range(10)]
    assert len(ProxyPoolDictSyncService._map_api_payload(raw, limit=3)) == 3


def test_host_port_from_server():
    assert ProxyPoolDictSyncService._host_port_from_server('http://1.2.3.4:8080') == '1.2.3.4:8080'
    assert ProxyPoolDictSyncService._host_port_from_server('https://5.6.7.8:443') == '5.6.7.8:443'


@pytest.mark.asyncio
async def test_fetch_skips_when_disabled():
    with patch(
        'knowledge_content.service.proxy_pool_dict_sync_service.ProxyPoolConfig'
    ) as cfg:
        cfg.proxy_pool_sync_enabled = False
        result = await ProxyPoolDictSyncService.fetch_from_api()
    assert result == {'skipped': True, 'reason': 'disabled'}


@pytest.mark.asyncio
async def test_fetch_keeps_old_on_empty_remote():
    with (
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.ProxyPoolConfig'
        ) as cfg,
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_insert_dict_rows',
            new_callable=AsyncMock,
        ) as insert,
    ):
        _enable_cfg(cfg)
        result = await ProxyPoolDictSyncService.fetch_from_api()

    assert result['skipped'] is True
    assert result['reason'] == 'empty_remote'
    insert.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_skips_when_all_already_exist():
    api_rows = [{'proxy': '9.9.9.9:8080', 'https': False, 'last_status': True}]
    with (
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.ProxyPoolConfig'
        ) as cfg,
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
            return_value=api_rows,
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_load_existing_servers',
            new_callable=AsyncMock,
            return_value={'http://9.9.9.9:8080'},
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_insert_dict_rows',
            new_callable=AsyncMock,
        ) as insert,
    ):
        _enable_cfg(cfg)
        result = await ProxyPoolDictSyncService.fetch_from_api()

    assert result['skipped'] is True
    assert result['reason'] == 'no_new'
    assert result['added'] == 0
    insert.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_inserts_only_new_servers():
    api_rows = [
        {'proxy': '9.9.9.9:8080', 'https': False, 'region': 'HK', 'last_status': True},
        {'proxy': '8.8.8.8:8080', 'https': False, 'region': 'US', 'last_status': True},
    ]
    redis = MagicMock()
    redis.set = AsyncMock()

    with (
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.ProxyPoolConfig'
        ) as cfg,
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
            return_value=api_rows,
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_load_existing_servers',
            new_callable=AsyncMock,
            return_value={'http://9.9.9.9:8080'},
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_next_dict_sort',
            new_callable=AsyncMock,
            return_value=10,
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_insert_dict_rows',
            new_callable=AsyncMock,
            return_value=1,
        ) as insert,
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.DictDataDao.query_dict_data_list',
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.RedisContext.get_redis',
            return_value=redis,
        ),
    ):
        _enable_cfg(cfg)
        result = await ProxyPoolDictSyncService.fetch_from_api()

    assert result == {
        'skipped': False,
        'fetched': 2,
        'existing': 1,
        'added': 1,
    }
    insert.assert_awaited_once()
    added_rows = insert.await_args.args[0]
    assert len(added_rows) == 1
    assert added_rows[0].dict_value == '{"server":"http://8.8.8.8:8080"}'
    assert added_rows[0].dict_sort == 10
    redis.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_skips_when_verify_disabled():
    with patch(
        'knowledge_content.service.proxy_pool_dict_sync_service.ProxyPoolConfig'
    ) as cfg:
        _enable_cfg(cfg)
        cfg.proxy_pool_verify_enabled = False
        result = await ProxyPoolDictSyncService.cleanup_dead()
    assert result == {'skipped': True, 'reason': 'verify_disabled'}


@pytest.mark.asyncio
async def test_cleanup_removes_dead_and_notifies_source():
    nodes = [
        _DictProxyNode(dict_code=1, proxy='1.1.1.1:80', server='http://1.1.1.1:80'),
        _DictProxyNode(dict_code=2, proxy='2.2.2.2:80', server='http://2.2.2.2:80'),
    ]

    async def _probe(server: str, verify_url: str, timeout: int) -> bool:
        return server.endswith('1.1.1.1:80')

    with (
        patch(
            'knowledge_content.service.proxy_pool_dict_sync_service.ProxyPoolConfig'
        ) as cfg,
        patch.object(
            ProxyPoolDictSyncService,
            '_load_dict_nodes',
            new_callable=AsyncMock,
            return_value=nodes,
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_probe_proxy',
            new=_probe,
        ),
        patch.object(
            ProxyPoolDictSyncService,
            '_delete_dict_nodes',
            new_callable=AsyncMock,
            return_value=1,
        ) as delete_dict,
        patch.object(
            ProxyPoolDictSyncService,
            '_delete_dead_from_source',
            new_callable=AsyncMock,
        ) as delete_src,
        patch.object(
            ProxyPoolDictSyncService,
            '_refresh_dict_cache',
            new_callable=AsyncMock,
        ) as refresh,
    ):
        _enable_cfg(cfg)
        result = await ProxyPoolDictSyncService.cleanup_dead()

    assert result == {'skipped': False, 'checked': 2, 'alive': 1, 'removed': 1}
    delete_dict.assert_awaited_once()
    dead_arg = delete_dict.await_args.args[0]
    assert len(dead_arg) == 1
    assert dead_arg[0].proxy == '2.2.2.2:80'
    delete_src.assert_awaited_once()
    refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_probe_proxy_accepts_2xx():
    response = MagicMock()
    response.status_code = 200
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    with patch(
        'knowledge_content.service.proxy_pool_dict_sync_service.httpx.AsyncClient',
        return_value=client,
    ):
        ok = await ProxyPoolDictSyncService._probe_proxy(
            'http://1.2.3.4:8080',
            'https://www.baidu.com',
            8,
        )
    assert ok is True
