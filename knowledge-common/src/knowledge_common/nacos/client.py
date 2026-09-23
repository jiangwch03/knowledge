"""Nacos 服务注册 / 发现（官方 nacos-sdk-python）。"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

from v2.nacos import (
    ClientConfigBuilder,
    DeregisterInstanceParam,
    GRPCConfig,
    ListInstanceParam,
    NacosNamingService,
    RegisterInstanceParam,
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
    """官方 Naming SDK 的薄封装：注册、下线、选实例。心跳由 SDK 维持。"""

    def __init__(self) -> None:
        self._sdk: NacosNamingService | None = None
        self._rr: dict[str, Any] = {}
        self._rr_key: dict[str, tuple] = {}
        self._registered: tuple[str, str, int] | None = None

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

    async def register(
        self,
        service_name: str,
        *,
        ip: str | None = None,
        port: int | None = None,
        metadata: dict[str, str] | None = None,
    ) -> NacosInstance:
        reg_ip = (ip or NacosConfig.nacos_register_ip or '').strip() or IPUtil.get_local_ip()
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
            '[Nacos] registered service={} ip={} port={} group={}',
            service_name,
            reg_ip,
            reg_port,
            group,
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
        if sdk is None:
            return
        try:
            await sdk.shutdown()
        except Exception as e:
            logger.warning('[Nacos] shutdown failed: {}', e)

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
        instances: list[NacosInstance] = []
        for host in hosts:
            meta = host.metadata if isinstance(host.metadata, dict) else None
            instances.append(
                NacosInstance(
                    ip=str(host.ip),
                    port=int(host.port),
                    healthy=bool(host.healthy),
                    metadata={str(k): str(v) for k, v in meta.items()} if meta else None,
                )
            )
        return instances

    async def select_one(self, service_name: str) -> NacosInstance:
        instances = await self.list_instances(service_name, healthy_only=True)
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
