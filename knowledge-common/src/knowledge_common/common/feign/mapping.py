"""声明式调用，对齐 @FeignClient + @GetMapping / @PostMapping。

方法体不执行。路径里的 {参数名} 用同名实参替换；GET 的 BaseModel 当查询参数，POST 的 BaseModel 当请求体；返回类型决定解包。
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from typing import Any, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from knowledge_common.common.feign.feign import Feign
from knowledge_common.common.feign.feign_client import FeignClient
from knowledge_common.common.feign.feign_page import FeignAckVo, FeignDataVo, FeignPageVo
from knowledge_common.exceptions.exception import ServiceException

_PATH_VAR = re.compile(r'\{([^{}]+)\}')


def feign_client(
    *,
    name: str,
    path: str = '',
    url: str = '',
    timeout: float | None = None,
) -> Callable[[type], type]:
    """标在 Client 类上，对应 @FeignClient。timeout 是该客户端默认读超时（秒）。"""

    def decorate(cls: type) -> type:
        cls._FEIGN = FeignClient(name=name, path=path, url=url, timeout=timeout)
        return cls

    return decorate


def get_mapping(path: str, *, timeout: float | None = None) -> Callable:
    """对应 @GetMapping。"""
    return _mapping('GET', path, timeout=timeout)


def post_mapping(path: str, *, timeout: float | None = None) -> Callable:
    """对应 @PostMapping。"""
    return _mapping('POST', path, timeout=timeout)


def _mapping(method: str, path: str, *, timeout: float | None) -> Callable:
    def decorate(fn: Callable) -> classmethod:
        async def wrapper(cls: type, *args: Any, **kwargs: Any) -> Any:
            client = getattr(cls, '_FEIGN', None)
            if not isinstance(client, FeignClient):
                raise ServiceException(message=f'{cls.__name__} 未声明 @feign_client')
            arguments = _bind_args(fn, cls, args, kwargs)
            url_path = _fill_path(path, arguments)
            body = _model_arg(path, arguments)
            return await _invoke(method, client, url_path, fn, body, timeout or client.timeout)

        return classmethod(wrapper)

    return decorate


def _bind_args(fn: Callable, cls: type, args: tuple, kwargs: dict) -> dict[str, Any]:
    bound = inspect.signature(fn).bind(cls, *args, **kwargs)
    bound.apply_defaults()
    return {key: value for key, value in bound.arguments.items() if key != 'cls'}


def _fill_path(path: str, arguments: dict[str, Any]) -> str:
    names = _PATH_VAR.findall(path)
    try:
        return path.format(**{name: arguments[name] for name in names})
    except KeyError as e:
        raise ServiceException(message=f'路径参数缺失: {path}') from e


def _model_arg(path: str, arguments: dict[str, Any]) -> BaseModel | None:
    names = set(_PATH_VAR.findall(path))
    models = [value for key, value in arguments.items() if key not in names and isinstance(value, BaseModel)]
    if len(models) > 1:
        raise ServiceException(message='一个接口只接受一个请求对象')
    return models[0] if models else None


def _generic_origin(return_type: Any) -> tuple[Any, tuple[Any, ...]]:
    """typing 泛型与 Pydantic 参数化模型都能取出原始类和类型参数。"""
    origin = get_origin(return_type)
    if origin is not None:
        return origin, get_args(return_type)
    meta = getattr(return_type, '__pydantic_generic_metadata__', None) or {}
    args = tuple(meta.get('args') or ())
    if meta.get('origin') is not None and args:
        return meta['origin'], args
    return return_type, ()


async def _invoke(
    method: str,
    client: FeignClient,
    path: str,
    fn: Callable,
    body: BaseModel | None,
    timeout: float | None,
) -> Any:
    return_type = get_type_hints(fn).get('return')
    origin, args = _generic_origin(return_type)
    if origin is FeignPageVo and args:
        return await Feign.get_page(client, path, row_model=args[0], params=body, timeout=timeout)
    if origin is FeignDataVo and args:
        model = args[0]
        if method == 'GET':
            return await Feign.get_data(client, path, model=model, params=body, timeout=timeout)
        return await Feign.post_data(client, path, model=model, body=body, timeout=timeout)
    if return_type is FeignAckVo or origin is FeignAckVo:
        return await Feign.post(client, path, body=body, timeout=timeout)
    raise ServiceException(message=f'{fn.__name__} 返回类型须为 FeignPageVo、FeignDataVo 或 FeignAckVo')
