"""OpenFeign 调用入口，对齐 Feign + LoadBalancer。

- FeignClient.url 非空：直连，绕过 Nacos（本地调试）
- 否则经 Nacos 选实例；发现失败直接抛错，无静态兜底
- 传输失败换下一实例重试（对齐 Ribbon MaxAutoRetriesNextServer）
- 解包本仓库 ResponseUtil 的 code/data/rows 约定
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from knowledge_common.common.feign.feign_client import FeignClient
from knowledge_common.common.feign.feign_page import FeignAckVo, FeignDataVo, FeignPageVo
from knowledge_common.config.env import NacosConfig, RpcClientConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.nacos.client import NacosInstance
from knowledge_common.utils.log_util import logger

T = TypeVar('T', bound=BaseModel)

# 可换实例重试的网关/上游错误（业务 4xx / 业务 code 不重试）
_RETRYABLE_STATUS = frozenset({502, 503, 504})


@dataclass(frozen=True, slots=True)
class _ResolvedTarget:
    base_url: str
    instance: NacosInstance | None


class Feign:
    """按 FeignClient 发请求（classmethod，禁止实例化）。"""

    DEFAULT_TIMEOUT = 120.0

    @classmethod
    async def resolve_target(cls, client: FeignClient) -> _ResolvedTarget:
        # @FeignClient(url=...)：显式 url 直连，绕过 Nacos
        direct = (client.url or '').strip().rstrip('/')
        if direct:
            return _ResolvedTarget(base_url=direct, instance=None)

        if not NacosConfig.nacos_enabled:
            raise ServiceException(
                message=f'Nacos 未启用且未配置直连 url，无法解析服务: {client.name}'
            )
        try:
            from knowledge_common.nacos import get_nacos_client

            inst = await get_nacos_client().select_one(client.name)
            return _ResolvedTarget(base_url=f'http://{inst.ip}:{inst.port}', instance=inst)
        except ServiceException:
            raise
        except Exception as e:
            logger.opt(exception=True).error(
                '[Feign] Nacos 发现失败 service={} err={}',
                client.name,
                e,
            )
            raise ServiceException(
                message=f'Nacos 发现失败: service={client.name}, err={e}'
            ) from e

    @classmethod
    async def resolve_base_url(cls, client: FeignClient) -> str:
        return (await cls.resolve_target(client)).base_url

    @classmethod
    async def build_url(cls, client: FeignClient, path: str) -> str:
        base = await cls.resolve_base_url(client)
        return cls._compose_url(base, client, path)

    @classmethod
    def _compose_url(cls, base_url: str, client: FeignClient, path: str) -> str:
        root = (client.path or '').rstrip('/')
        suffix = path if path.startswith('/') else f'/{path}'
        return f'{base_url.rstrip("/")}{root}{suffix}'

    @classmethod
    def _biz(cls, payload: dict[str, Any]) -> tuple[int | None, str]:
        code = payload.get('code')
        msg = str(payload.get('msg') or payload.get('message') or '')
        return (int(code) if isinstance(code, int) else None, msg)

    @classmethod
    def _parse_payload(cls, payload: dict[str, Any], *, expect_page: bool = False) -> Any:
        # 业务码留给调用方判断，这里只拆包
        code, msg = cls._biz(payload)
        if expect_page:
            return FeignPageVo[Any](
                code=code,
                msg=msg,
                rows=payload.get('rows') or payload.get('data') or [],
                total=int(payload.get('total') or 0),
                page_num=int(payload.get('pageNum') or payload.get('page_num') or 1),
                page_size=int(payload.get('pageSize') or payload.get('page_size') or 10),
                has_next=bool(payload.get('hasNext') or payload.get('has_next') or False),
            )
        data = payload.get('data') if 'data' in payload else None
        return FeignDataVo[Any](code=code, msg=msg, data=data)

    @classmethod
    def _should_retry_http_error(cls, exc: httpx.HTTPError) -> bool:
        if isinstance(exc, httpx.TransportError):
            return True
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in _RETRYABLE_STATUS
        return False

    @classmethod
    def _mark_instance_failed(cls, client: FeignClient, instance: NacosInstance | None) -> None:
        if instance is None:
            return
        from knowledge_common.nacos import get_nacos_client

        get_nacos_client().mark_unhealthy(client.name, instance.ip, instance.port)

    @classmethod
    def _dump_model(cls, value: BaseModel | dict[str, Any] | None) -> dict[str, Any] | None:
        """协议层序列化：仅 httpx 需要 dict，业务侧始终传 VO。"""
        if value is None:
            return None
        if isinstance(value, BaseModel):
            # userInfo 是本进程登录上下文，带 datetime，不能进 HTTP JSON。对端按 userId 自己查用户。
            return value.model_dump(
                by_alias=True,
                exclude_none=True,
                exclude={'userInfo'},
                mode='json',
            )
        return value

    @classmethod
    async def request(
        cls,
        method: str,
        client: FeignClient,
        path: str,
        *,
        params: BaseModel | dict[str, Any] | None = None,
        json_body: BaseModel | dict[str, Any] | None = None,
        expect_page: bool = False,
        timeout: float | None = None,
    ) -> Any:
        headers = {'Content-Type': 'application/json'}
        max_next = max(0, int(RpcClientConfig.rpc_max_retries_next_server))
        attempts = 1 + max_next
        last_error: Exception | None = None
        tried_hosts: set[str] = set()
        query = cls._dump_model(params)
        payload_body = cls._dump_model(json_body)

        for attempt in range(attempts):
            target = await cls.resolve_target(client)
            host_key = urlparse(target.base_url).netloc or target.base_url
            # 换实例重试时跳过已试过的 host（避免 RR 又抽到同一台）
            if host_key in tried_hosts and target.instance is not None and attempt < attempts - 1:
                cls._mark_instance_failed(client, target.instance)
                continue
            tried_hosts.add(host_key)
            url = cls._compose_url(target.base_url, client, path)
            try:
                # 内部地址直连。trust_env 会把 127.0.0.1 送进 HTTP 代理，请求挂住直到读超时。
                async with httpx.AsyncClient(
                    timeout=timeout or cls.DEFAULT_TIMEOUT,
                    trust_env=False,
                ) as client_http:
                    resp = await client_http.request(
                        method, url, params=query, json=payload_body, headers=headers
                    )
                    resp.raise_for_status()
                    payload = resp.json()
            except httpx.HTTPError as e:
                last_error = e
                retryable = cls._should_retry_http_error(e) and target.instance is not None
                if retryable and attempt < attempts - 1:
                    cls._mark_instance_failed(client, target.instance)
                    logger.warning(
                        '[Feign] 实例调用失败，换下一实例重试 attempt={}/{} url={} err={}',
                        attempt + 1,
                        attempts,
                        url,
                        e,
                    )
                    continue
                detail = str(e).strip() or type(e).__name__
                logger.opt(exception=True).error('[Feign] 调用失败 url={} err={}', url, detail)
                raise ServiceException(message=f'跨服务调用失败: {detail}') from e

            if not isinstance(payload, dict):
                raise ServiceException(message='跨服务响应非 JSON 对象')
            # 业务 code 失败不换实例重试（对齐 Feign：仅传输层 / 下一台）
            return cls._parse_payload(payload, expect_page=expect_page)

        raise ServiceException(message=f'跨服务调用失败: {last_error}')

    @classmethod
    async def get_data(
        cls,
        client: FeignClient,
        path: str,
        *,
        model: type[T],
        params: BaseModel | None = None,
        timeout: float | None = None,
    ) -> FeignDataVo[T]:
        body = await cls.request(
            'GET',
            client,
            path,
            params=params,
            timeout=timeout,
        )
        assert isinstance(body, FeignDataVo)
        data = body.data
        item = model.model_validate(data) if isinstance(data, dict) else None
        return FeignDataVo[T](code=body.code, msg=body.msg, data=item)

    @classmethod
    async def get_page(
        cls,
        client: FeignClient,
        path: str,
        *,
        row_model: type[T],
        params: BaseModel | None = None,
        timeout: float | None = None,
    ) -> FeignPageVo[T]:
        page = await cls.request(
            'GET',
            client,
            path,
            params=params,
            expect_page=True,
            timeout=timeout,
        )
        assert isinstance(page, FeignPageVo)
        return FeignPageVo[T](
            code=page.code,
            msg=page.msg,
            rows=[row_model.model_validate(row) for row in page.rows],
            total=page.total,
            page_num=page.page_num,
            page_size=page.page_size,
            has_next=page.has_next,
        )

    @classmethod
    async def post_data(
        cls,
        client: FeignClient,
        path: str,
        *,
        model: type[T],
        body: BaseModel | None = None,
        timeout: float | None = None,
    ) -> FeignDataVo[T]:
        result = await cls.request(
            'POST',
            client,
            path,
            json_body=body,
            timeout=timeout,
        )
        assert isinstance(result, FeignDataVo)
        data = result.data
        item = model.model_validate(data) if isinstance(data, dict) else None
        return FeignDataVo[T](code=result.code, msg=result.msg, data=item)

    @classmethod
    async def post(
        cls,
        client: FeignClient,
        path: str,
        *,
        body: BaseModel | None = None,
        timeout: float | None = None,
    ) -> FeignAckVo:
        """POST 无强类型 data（如仅返回成功消息）。"""
        result = await cls.request(
            'POST',
            client,
            path,
            json_body=body,
            timeout=timeout,
        )
        assert isinstance(result, FeignDataVo)
        return FeignAckVo(code=result.code, msg=result.msg)
