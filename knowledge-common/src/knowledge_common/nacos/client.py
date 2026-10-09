"""Nacos 服务注册 / 发现（官方 nacos-sdk-python）。

对齐 Spring Cloud Alibaba Nacos Discovery 的核心能力：
- 注册 / 下线（ephemeral）
- 客户端心跳：由 SDK 按 nacos_beat_interval_seconds 维持
- 本机注册 IP 进程内缓存（类比 InetUtils）
- 服务实例本地缓存 + subscribe 推送更新（类比 NamingService 本地缓存）
- 轮询选实例（类比 Ribbon RoundRobin）
"""

from __future__ import annotations

import asyncio
import itertools
import time
from dataclasses import dataclass
from typing import Any

from v2.nacos import (
    ClientConfigBuilder,
    DeregisterInstanceParam,
    GRPCConfig,
    ListInstanceParam,
    NacosNamingService,
    RegisterInstanceParam,
    SubscribeServiceParam,
)

from knowledge_common.config.env import AppConfig, NacosConfig
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.server_util import IPUtil


@dataclass(frozen=True)
class NacosInstance:
    ip: str
    port: int
    healthy: bool = True
    metadata: dict[str, str] | None = None


class NacosNamingClient:
    """官方 Naming SDK 封装：注册、发现缓存、选实例。心跳由 SDK 维持。"""

    def __init__(self) -> None:
        self._sdk: NacosNamingService | None = None
        self._rr: dict[str, Any] = {}
        self._rr_key: dict[str, tuple] = {}
        self._registered: tuple[str, str, int] | None = None
        # 本机注册 IP 缓存（进程内只解析一次）
        self._cached_register_ip: str | None = None
        # 服务实例本地缓存：service_name -> instances
        self._instance_cache: dict[str, list[NacosInstance]] = {}
        self._subscribed: set[str] = set()
        self._cache_lock = asyncio.Lock()
        # 调用失败临时拉黑：(service, ip, port) -> expire_monotonic
        self._blacklist: dict[tuple[str, str, int], float] = {}

    def _build_config(self):
        addr = _normalize_server_addr(NacosConfig.nacos_server_addr)
        builder = (
            ClientConfigBuilder()
            .server_address(addr)
            .log_level('INFO')
            .heart_beat_interval(int(float(NacosConfig.nacos_beat_interval_seconds) * 1000))
            .grpc_config(GRPCConfig(grpc_timeout=5000))
        )
        ns = (NacosConfig.nacos_namespace or '').strip()
        if ns:
            builder = builder.namespace_id(ns)
        user = (NacosConfig.nacos_username or '').strip()
        if user:
            builder = builder.username(user).password(NacosConfig.nacos_password or '')
        return builder.build()

    async def _client(self) -> NacosNamingService:
        if self._sdk is None:
            self._sdk = await NacosNamingService.create_naming_service(self._build_config())
        return self._sdk

    def resolve_register_ip(self, ip: str | None = None) -> str:
        """解析并缓存本机注册 IP（优先配置，其次出站网卡 IP）。"""
        if ip and ip.strip():
            return ip.strip()
        configured = (NacosConfig.nacos_register_ip or '').strip()
        if configured:
            return configured
        if self._cached_register_ip:
            return self._cached_register_ip
        network_ips = IPUtil.get_network_ips()
        resolved = network_ips[0] if network_ips else IPUtil.get_local_ip()
        self._cached_register_ip = resolved
        logger.info('[Nacos] cached register ip={}', resolved)
        return resolved

    @staticmethod
    def _to_instances(hosts: list[Any], *, healthy_only: bool) -> list[NacosInstance]:
        instances: list[NacosInstance] = []
        for host in hosts:
            healthy = bool(getattr(host, 'healthy', True))
            if healthy_only and not healthy:
                continue
            enabled = getattr(host, 'enabled', True)
            if enabled is False:
                continue
            meta = getattr(host, 'metadata', None)
            meta_dict = meta if isinstance(meta, dict) else None
            instances.append(
                NacosInstance(
                    ip=str(host.ip),
                    port=int(host.port),
                    healthy=healthy,
                    metadata={str(k): str(v) for k, v in meta_dict.items()} if meta_dict else None,
                )
            )
        return instances

    async def register(
        self,
        service_name: str,
        *,
        ip: str | None = None,
        port: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> NacosInstance:
        reg_ip = self.resolve_register_ip(ip)
        reg_port = int(port or AppConfig.app_port)
        meta = metadata or {
            'appName': AppConfig.app_name,
            'rootPath': AppConfig.app_root_path,
        }
        group = NacosConfig.nacos_group or 'DEFAULT_GROUP'
        client = await self._client()
        ok = await client.register_instance(
            request=RegisterInstanceParam(
                service_name=service_name,
                group_name=group,
                ip=reg_ip,
                port=reg_port,
                weight=float(NacosConfig.nacos_weight),
                cluster_name='DEFAULT',
                metadata=meta,
                enabled=True,
                healthy=True,
                ephemeral=True,
            )
        )
        if not ok:
            raise RuntimeError(f'Nacos register failed: service={service_name}')
        self._registered = (service_name, reg_ip, reg_port)
        logger.info(
            '[Nacos] registered service={} ip={} port={} group={} (heartbeat by SDK, interval={}s)',
            service_name,
            reg_ip,
            reg_port,
            group,
            NacosConfig.nacos_beat_interval_seconds,
        )
        return NacosInstance(ip=reg_ip, port=reg_port, metadata=meta)

    async def deregister(self) -> None:
        registered = self._registered
        self._registered = None
        try:
            if registered and self._sdk is not None:
                service_name, reg_ip, reg_port = registered
                await self._sdk.deregister_instance(
                    request=DeregisterInstanceParam(
                        service_name=service_name,
                        group_name=NacosConfig.nacos_group or 'DEFAULT_GROUP',
                        ip=reg_ip,
                        port=reg_port,
                        cluster_name='DEFAULT',
                        ephemeral=True,
                    )
                )
                logger.info('[Nacos] deregistered service={} ip={} port={}', service_name, reg_ip, reg_port)
        except Exception as e:
            logger.warning('[Nacos] deregister failed: {}', e)
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        sdk = self._sdk
        self._sdk = None
        self._subscribed.clear()
        self._instance_cache.clear()
        self._blacklist.clear()
        self._rr.clear()
        self._rr_key.clear()
        if sdk is None:
            return
        try:
            await sdk.shutdown()
        except Exception as e:
            logger.warning('[Nacos] shutdown failed: {}', e)

    def mark_unhealthy(self, service_name: str, ip: str, port: int) -> None:
        """调用失败后临时隔离实例（类比 LoadBalancer 失败摘除）。"""
        ttl = float(NacosConfig.nacos_instance_blacklist_seconds or 0)
        if ttl <= 0:
            return
        key = (service_name, ip, int(port))
        self._blacklist[key] = time.monotonic() + ttl
        self._rr.pop(service_name, None)
        self._rr_key.pop(service_name, None)
        logger.warning(
            '[Nacos] blacklist instance service={} ip={} port={} ttl={}s',
            service_name,
            ip,
            port,
            ttl,
        )

    def _purge_blacklist(self) -> None:
        now = time.monotonic()
        expired = [k for k, exp in self._blacklist.items() if exp <= now]
        for k in expired:
            self._blacklist.pop(k, None)

    def _filter_blacklisted(
        self,
        service_name: str,
        instances: list[NacosInstance],
    ) -> list[NacosInstance]:
        self._purge_blacklist()
        if not self._blacklist:
            return instances
        alive = [
            inst
            for inst in instances
            if (service_name, inst.ip, inst.port) not in self._blacklist
        ]
        # 全被拉黑时放行原列表，避免无实例可用
        return alive or instances

    async def list_instances(self, service_name: str, *, healthy_only: bool = True) -> list[NacosInstance]:
        client = await self._client()
        hosts = await client.list_instances(
            ListInstanceParam(
                service_name=service_name,
                group_name=NacosConfig.nacos_group or 'DEFAULT_GROUP',
                healthy_only=True if healthy_only else None,
                subscribe=False,
            )
        )
        return self._to_instances(hosts, healthy_only=healthy_only)

    async def _ensure_subscribed(self, service_name: str) -> None:
        """首次访问时订阅，后续靠推送更新本地缓存。"""
        if service_name in self._subscribed:
            return
        async with self._cache_lock:
            if service_name in self._subscribed:
                return
            group = NacosConfig.nacos_group or 'DEFAULT_GROUP'

            async def _on_change(hosts: list[Any]) -> None:
                instances = self._to_instances(hosts, healthy_only=True)
                self._instance_cache[service_name] = instances
                # 推送刷新后清掉该服务拉黑，交给新健康列表
                stale = [k for k in self._blacklist if k[0] == service_name]
                for k in stale:
                    self._blacklist.pop(k, None)
                self._rr.pop(service_name, None)
                self._rr_key.pop(service_name, None)
                logger.info(
                    '[Nacos] instance cache updated service={} count={}',
                    service_name,
                    len(instances),
                )

            client = await self._client()
            await client.subscribe(
                SubscribeServiceParam(
                    service_name=service_name,
                    group_name=group,
                    subscribe_callback=_on_change,
                )
            )
            # 订阅后立即拉一次，预热本地缓存
            warm = await self.list_instances(service_name, healthy_only=True)
            self._instance_cache[service_name] = warm
            self._subscribed.add(service_name)
            logger.info(
                '[Nacos] subscribed service={} cached={}',
                service_name,
                len(warm),
            )

    async def select_one(self, service_name: str) -> NacosInstance:
        """轮询选取健康实例；优先读本地订阅缓存，跳过临时拉黑。"""
        try:
            await self._ensure_subscribed(service_name)
        except Exception as e:
            logger.warning('[Nacos] subscribe failed service={} fallback list: {}', service_name, e)
            instances = await self.list_instances(service_name, healthy_only=True)
            return self._pick_rr(service_name, self._filter_blacklisted(service_name, instances))

        instances = self._instance_cache.get(service_name) or []
        if not instances:
            # 缓存空：再拉一次并写回
            instances = await self.list_instances(service_name, healthy_only=True)
            self._instance_cache[service_name] = instances
        return self._pick_rr(service_name, self._filter_blacklisted(service_name, instances))

    def _pick_rr(self, service_name: str, instances: list[NacosInstance]) -> NacosInstance:
        if not instances:
            raise RuntimeError(f'Nacos 无可用实例: service={service_name}')
        key = (service_name, tuple((i.ip, i.port) for i in instances))
        if self._rr_key.get(service_name) != key:
            self._rr[service_name] = itertools.cycle(instances)
            self._rr_key[service_name] = key
        return next(self._rr[service_name])


_client: NacosNamingClient | None = None


def get_nacos_client() -> NacosNamingClient:
    global _client
    if _client is None:
        _client = NacosNamingClient()
    return _client


def _normalize_server_addr(addr: str) -> str:
    raw = (addr or '').strip().rstrip('/')
    for prefix in ('http://', 'https://'):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
    return raw
