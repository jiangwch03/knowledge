"""外部代理池 → 系统字典：拉取与清理

与爬取业务解耦。
- 拉取：只新增字典里还没有的代理（不删、不覆盖）
- 清理：只删除探测不通的节点（不增）
两者写路径分离，可并行无互斥锁。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from knowledge_common.common.context import RedisContext
from knowledge_common.common.transactional import transactional
from knowledge_common.config.env import ProxyPoolConfig
from knowledge_common.mapper.dao.dict_dao import DictDataDao
from knowledge_common.redis import RedisKey
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.url_util import UrlUtil
from knowledge_common.vo.dict_vo import DictDataModel
from knowledge_content.enums.crawl_proxy_pool_dict_enum import CrawlProxyPoolDict

_SYNC_REMARK_PREFIX = 'proxy_pool_sync'
_DICT_VALUE_MAX_LEN = 100
_DICT_LABEL_MAX_LEN = 100


@dataclass(frozen=True, slots=True)
class _ProxyCandidate:
    """拉取候选：host:port + 待写入字典行"""

    proxy: str
    server: str
    row: DictDataModel


@dataclass(frozen=True, slots=True)
class _DictProxyNode:
    """字典中的待清理节点"""

    dict_code: int
    proxy: str
    server: str


class ProxyPoolDictSyncService:
    """外部 proxy_pool ↔ crawl_proxy_pool 字典：拉取（只增）/ 清理（只删）"""

    @classmethod
    async def fetch_from_api(cls) -> dict[str, Any]:
        """
        拉取任务：GET /all → 丢弃 last_status=false → 排除字典已有 server → 只插入新增。

        不删除、不覆盖已有行；探测与剔除由清理任务负责。
        """
        if not ProxyPoolConfig.proxy_pool_sync_enabled:
            logger.info('[ProxyPool] 拉取已禁用（proxy_pool_sync_enabled=false），跳过')
            return {'skipped': True, 'reason': 'disabled'}

        base = ProxyPoolConfig.proxy_pool_api_base_url.rstrip('/')
        url = f'{base}/all/'
        raw = await UrlUtil.async_http_get(
            url,
            list,
            timeout=ProxyPoolConfig.proxy_pool_request_timeout,
        )

        candidates = cls._map_api_payload(raw, limit=ProxyPoolConfig.proxy_pool_sync_limit)
        if not candidates:
            logger.info('[ProxyPool] 拉取无候选: url={}', url)
            return {'skipped': True, 'reason': 'empty_remote', 'fetched': 0}

        existing_servers = await cls._load_existing_servers()
        to_add = [c for c in candidates if c.server not in existing_servers]
        if not to_add:
            logger.info(
                '[ProxyPool] 拉取无新增: fetched={}, already_have={}',
                len(candidates),
                len(existing_servers),
            )
            return {
                'skipped': True,
                'reason': 'no_new',
                'fetched': len(candidates),
                'existing': len(existing_servers),
                'added': 0,
            }

        start_sort = await cls._next_dict_sort()
        for offset, candidate in enumerate(to_add):
            candidate.row.dict_sort = start_sort + offset

        added = await cls._insert_dict_rows([c.row for c in to_add])
        await cls._refresh_dict_cache()
        logger.info(
            '[ProxyPool] 拉取完成: fetched={}, existing={}, added={}',
            len(candidates),
            len(existing_servers),
            added,
        )
        return {
            'skipped': False,
            'fetched': len(candidates),
            'existing': len(existing_servers),
            'added': added,
        }

    @classmethod
    async def cleanup_dead(cls) -> dict[str, Any]:
        """
        清理任务：读字典 → 存活探测 → 只删除不通节点；可选回调源池 /delete。

        不新增行；与拉取任务写路径不交叉。空窗靠 30 秒拉取任务补回。
        """
        if not ProxyPoolConfig.proxy_pool_sync_enabled:
            logger.info('[ProxyPool] 清理已禁用（proxy_pool_sync_enabled=false），跳过')
            return {'skipped': True, 'reason': 'disabled'}
        if not ProxyPoolConfig.proxy_pool_verify_enabled:
            logger.info('[ProxyPool] 清理已关闭（proxy_pool_verify_enabled=false），跳过')
            return {'skipped': True, 'reason': 'verify_disabled'}

        nodes = await cls._load_dict_nodes()
        if not nodes:
            logger.info('[ProxyPool] 清理：字典无节点，跳过')
            return {'skipped': True, 'reason': 'empty_dict', 'checked': 0}

        alive, dead = await cls._probe_nodes(nodes)
        if dead:
            await cls._delete_dict_nodes(dead)
            if ProxyPoolConfig.proxy_pool_delete_dead:
                base = ProxyPoolConfig.proxy_pool_api_base_url.rstrip('/')
                await cls._delete_dead_from_source(
                    api_base=base,
                    dead_proxies=[n.proxy for n in dead],
                )
            await cls._refresh_dict_cache()

        logger.info(
            '[ProxyPool] 清理完成: checked={}, alive={}, removed={}',
            len(nodes),
            len(alive),
            len(dead),
        )
        return {
            'skipped': False,
            'checked': len(nodes),
            'alive': len(alive),
            'removed': len(dead),
        }

    @classmethod
    def _map_api_payload(cls, raw: list[Any], *, limit: int) -> list[_ProxyCandidate]:
        """将 proxy_pool /all 响应映射为候选；显式 last_status=false 的直接丢弃"""
        if not isinstance(raw, list):
            logger.warning('[ProxyPool] /all 响应非 list，跳过: type={}', type(raw).__name__)
            return []

        now = datetime.now()
        mapped: list[_ProxyCandidate] = []
        seen_servers: set[str] = set()

        for entry in raw:
            if len(mapped) >= max(limit, 0):
                break
            if not isinstance(entry, dict):
                continue

            if entry.get('last_status') is False:
                continue

            proxy = str(entry.get('proxy') or '').strip()
            if not proxy or ':' not in proxy:
                continue

            scheme = 'https' if entry.get('https') else 'http'
            server = f'{scheme}://{proxy}'
            if server in seen_servers:
                continue
            seen_servers.add(server)

            value = json.dumps({'server': server}, ensure_ascii=False, separators=(',', ':'))
            if len(value) > _DICT_VALUE_MAX_LEN:
                logger.warning('[ProxyPool] dict_value 超长跳过: len={}, server={}', len(value), server)
                continue

            region = str(entry.get('region') or '').strip()
            source = str(entry.get('source') or '').strip()
            label = f'{region}-{proxy}' if region else proxy
            label = label[:_DICT_LABEL_MAX_LEN]
            remark_parts = [_SYNC_REMARK_PREFIX]
            if source:
                remark_parts.append(f'source={source}')
            if region:
                remark_parts.append(f'region={region}')

            # DictDataModel 仅按 camelCase alias 接收构造参数（未开 populate_by_name）
            row = DictDataModel(
                dictSort=len(mapped) + 1,
                dictLabel=label,
                dictValue=value,
                dictType=CrawlProxyPoolDict.DICT_TYPE,
                isDefault='N',
                status='0',
                createBy=_SYNC_REMARK_PREFIX,
                createTime=now,
                updateBy=_SYNC_REMARK_PREFIX,
                updateTime=now,
                remark=' '.join(remark_parts),
            )
            mapped.append(_ProxyCandidate(proxy=proxy, server=server, row=row))

        return mapped

    @classmethod
    async def _load_existing_servers(cls) -> set[str]:
        """字典中已有的 server 集合（用于拉取去重）"""
        rows = await DictDataDao.query_dict_data_list(CrawlProxyPoolDict.DICT_TYPE)
        servers: set[str] = set()
        for row in rows:
            if not getattr(row, 'dict_code', None):
                continue
            server = cls._server_from_dict_value(getattr(row, 'dict_value', None))
            if server:
                servers.add(server)
        return servers

    @classmethod
    async def _next_dict_sort(cls) -> int:
        """新增行起始 dict_sort = 当前最大 sort + 1"""
        rows = await DictDataDao.query_dict_data_list(CrawlProxyPoolDict.DICT_TYPE)
        max_sort = 0
        for row in rows:
            if not getattr(row, 'dict_code', None):
                continue
            sort_val = getattr(row, 'dict_sort', None)
            if isinstance(sort_val, int) and sort_val > max_sort:
                max_sort = sort_val
        return max_sort + 1

    @classmethod
    async def _load_dict_nodes(cls) -> list[_DictProxyNode]:
        """从字典加载可探测节点"""
        rows = await DictDataDao.query_dict_data_list(CrawlProxyPoolDict.DICT_TYPE)
        nodes: list[_DictProxyNode] = []
        for row in rows:
            dict_code = getattr(row, 'dict_code', None)
            if not dict_code:
                continue
            server = cls._server_from_dict_value(getattr(row, 'dict_value', None))
            if not server:
                continue
            proxy = cls._host_port_from_server(server)
            if not proxy:
                continue
            nodes.append(_DictProxyNode(dict_code=int(dict_code), proxy=proxy, server=server))
        return nodes

    @staticmethod
    def _server_from_dict_value(value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        server = data.get('server') or data.get('url')
        return str(server).strip() if server else None

    @staticmethod
    def _host_port_from_server(server: str) -> str | None:
        """http://host:port → host:port（供源池 /delete）"""
        parsed = urlparse(server)
        if parsed.hostname and parsed.port:
            return f'{parsed.hostname}:{parsed.port}'
        if '://' not in server and ':' in server:
            return server.strip()
        return None

    @classmethod
    async def _probe_nodes(
        cls,
        nodes: list[_DictProxyNode],
    ) -> tuple[list[_DictProxyNode], list[_DictProxyNode]]:
        """并发探测；返回 (存活, 死亡)"""
        verify_url = ProxyPoolConfig.proxy_pool_verify_url
        timeout = ProxyPoolConfig.proxy_pool_verify_timeout
        concurrency = max(ProxyPoolConfig.proxy_pool_verify_concurrency, 1)
        sem = asyncio.Semaphore(concurrency)

        async def _one(node: _DictProxyNode) -> tuple[_DictProxyNode, bool]:
            async with sem:
                ok = await cls._probe_proxy(node.server, verify_url, timeout)
                return node, ok

        results = await asyncio.gather(*[_one(n) for n in nodes])
        alive: list[_DictProxyNode] = []
        dead: list[_DictProxyNode] = []
        for node, ok in results:
            if ok:
                alive.append(node)
            else:
                dead.append(node)

        logger.info(
            '[ProxyPool] 清理探测结束: total={}, alive={}, dead={}, verify_url={}',
            len(nodes),
            len(alive),
            len(dead),
            verify_url,
        )
        return alive, dead

    @staticmethod
    async def _probe_proxy(server: str, verify_url: str, timeout: int) -> bool:
        """经代理访问 verify_url，HTTP 2xx/3xx 视为存活"""
        try:
            async with httpx.AsyncClient(
                proxy=server,
                timeout=timeout,
                follow_redirects=True,
                trust_env=False,
                verify=False,
            ) as client:
                response = await client.get(verify_url)
                return 200 <= response.status_code < 400
        except Exception:
            return False

    @classmethod
    @transactional()
    async def _insert_dict_rows(cls, items: list[DictDataModel]) -> int:
        """只插入新行，不删除已有数据"""
        for item in items:
            await DictDataDao.add_dict_data_dao(item)
        return len(items)

    @classmethod
    @transactional()
    async def _delete_dict_nodes(cls, dead: list[_DictProxyNode]) -> int:
        """从字典删除死亡节点"""
        codes = [n.dict_code for n in dead]
        if not codes:
            return 0
        return await DictDataDao.delete_dict_data_by_codes(codes)

    @classmethod
    async def _delete_dead_from_source(cls, *, api_base: str, dead_proxies: list[str]) -> None:
        """回调源池 /delete 剔除探测失败的代理（失败仅记日志）"""
        if not dead_proxies:
            return

        deleted = 0
        async with httpx.AsyncClient(
            timeout=ProxyPoolConfig.proxy_pool_request_timeout,
            follow_redirects=True,
            proxy=None,
            trust_env=False,
        ) as client:
            for proxy in dead_proxies:
                delete_url = f'{api_base}/delete/?proxy={quote(proxy, safe=":")}'
                try:
                    response = await client.get(delete_url)
                    if response.status_code == 200:
                        deleted += 1
                    else:
                        logger.warning(
                            '[ProxyPool] 源池剔除失败: proxy={}, status={}',
                            proxy,
                            response.status_code,
                        )
                except Exception as err:
                    logger.warning('[ProxyPool] 源池剔除异常: proxy={}, err={}', proxy, err)

        logger.info('[ProxyPool] 源池剔除完成: requested={}, deleted_ok={}', len(dead_proxies), deleted)

    @classmethod
    async def _refresh_dict_cache(cls) -> None:
        """按 dict_type 回填 Redis 字典缓存"""
        dict_type = CrawlProxyPoolDict.DICT_TYPE
        rows = await DictDataDao.query_dict_data_list(dict_type)
        payload = [CamelCaseUtil.transform_result(row) for row in rows if row and getattr(row, 'dict_code', None)]
        redis = RedisContext.get_redis()
        await redis.set(
            RedisKey.sys_dict_key(dict_type),
            json.dumps(payload, ensure_ascii=False, default=str),
        )
