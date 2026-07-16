from typing import Any, TypeVar, cast, get_origin
from urllib.parse import ParseResult, urlparse

import httpx

from knowledge_common.exceptions.exception import ServiceException

T = TypeVar('T')


class UrlUtil:
    """
    URL 工具类

    提供 URL 校验、解析以及 HTTP 调用封装能力。
    """

    @classmethod
    def validate_and_parse_url(cls, url: str) -> ParseResult:
        """
        校验 URL 并解析，返回 ParseResult

        :param url: 待校验的 URL 字符串
        :return: urlparse 解析后的 ParseResult
        :raises ServiceException: URL 为空、格式无效或协议不受支持时抛出
        """
        if not url or not url.strip():
            raise ServiceException('URL不能为空')

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ServiceException(f'无效的URL格式: {url}')
        if parsed.scheme not in ('http', 'https'):
            raise ServiceException(f'不支持的URL协议: {parsed.scheme}，仅支持 http/https')

        return parsed

    @classmethod
    async def async_http_get(
        cls,
        url: str,
        response_type: type[T],
        timeout: int = 30,
        headers: dict | None = None,
    ) -> T:
        """
        异步 GET 请求封装，自动跟随重定向并按指定类型反序列化

        :param url: 目标 URL
        :param response_type: 响应反序列化目标类型，支持 httpx.Response / dict / list / Pydantic BaseModel / 普通 Dataclass
        :param timeout: 超时秒数，默认 30s
        :param headers: 自定义请求头，可选
        :return: 反序列化后的响应对象
        :raises ServiceException: HTTP 状态码非 200 或反序列化失败时抛出
        """
        # proxy=None：显式禁用代理，避免 httpx 自动从环境变量/PyCharm 配置中读取 HTTP_PROXY/HTTPS_PROXY
        async with httpx.AsyncClient(
            timeout=timeout, follow_redirects=True, proxy=None, trust_env=False,
        ) as client:
            # 1. 发送 GET 请求
            response = await client.get(url, headers=headers or {})

            # 2. 校验 HTTP 状态码，非 200 直接抛出异常
            if response.status_code != 200:
                raise ServiceException(f'HTTP请求失败，状态码: {response.status_code}，URL: {url}')

            # 3. 若需要原始响应对象，直接返回
            if response_type is httpx.Response:
                return cast(T, response)

            # 4. 解析响应体为 JSON
            try:
                data = response.json()
            except Exception as e:
                raise ServiceException(f'响应JSON解析失败，URL: {url}') from e

            # 5. 按 response_type 进行反序列化
            origin = get_origin(response_type)

            # 5.1 dict / list 泛型别名，直接返回 JSON 数据
            if origin in (dict, list):
                return cast(T, data)

            # 5.2 数据已是目标类型实例，直接返回
            if isinstance(data, response_type):
                return cast(T, data)

            # 5.3 Pydantic v2 风格模型
            model_validate = getattr(response_type, 'model_validate', None)
            if callable(model_validate):
                return cast(T, cast(Any, response_type).model_validate(data))

            # 5.4 普通 dataclass / VO 构造
            return cast(T, response_type(**data))
