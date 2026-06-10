import re
from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Literal

from knowledge_common.exceptions.exception import LoginException
from knowledge_common.entity.vo.user_vo import CurrentUserModel

if TYPE_CHECKING:
    from redis import asyncio as aioredis

# 定义上下文变量
# 存储当前请求的编译后的排除路由模式列表
current_exclude_patterns: ContextVar[
    list[dict[str, str | list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']] | re.Pattern]] | None
] = ContextVar('current_exclude_patterns', default=None)
# 存储当前用户信息
current_user: ContextVar[CurrentUserModel | None] = ContextVar('current_user', default=None)
# 存储当前可用的 Redis 客户端（server 生命周期级别，应用启动时设置一次）
current_redis: ContextVar['aioredis.Redis | None'] = ContextVar('current_redis', default=None)


class RequestContext:
    """
    请求上下文管理类，用于设置和清理上下文变量
    """

    @staticmethod
    def set_current_exclude_patterns(
        exclude_patterns: list[
            dict[str, str | list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']] | re.Pattern]
        ],
    ) -> Token:
        """
        设置当前请求的编译后的排除路由模式列表

        :param exclude_patterns: 编译后的排除路由模式列表
        :return: 上下文变量令牌，用于重置
        """
        return current_exclude_patterns.set(exclude_patterns)

    @staticmethod
    def get_current_exclude_patterns() -> list[
        dict[str, str | list[Literal['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']] | re.Pattern]
    ]:
        """
        获取当前请求的编译后的排除路由模式列表

        :return: 编译后的排除路由模式列表
        """
        _exclude_patterns = current_exclude_patterns.get()
        if _exclude_patterns is None:
            _exclude_patterns = []
        return _exclude_patterns

    @staticmethod
    def set_current_user(user: CurrentUserModel) -> Token:
        """
        设置当前用户信息

        :param user: 用户信息
        :return: 上下文变量令牌，用于重置
        """
        return current_user.set(user)

    @staticmethod
    def get_current_user() -> CurrentUserModel:
        """
        获取当前用户信息

        :return: 用户信息
        """
        _current_user = current_user.get()
        if _current_user is None:
            raise LoginException(data='', message='当前用户信息为空，请检查是否已登录')
        return _current_user

    @staticmethod
    def reset_current_exclude_patterns(token: Token) -> None:
        """
        重置当前请求的编译后的排除路由模式列表

        :param token: 设置编译后的排除路由模式列表时返回的令牌
        """
        current_exclude_patterns.reset(token)

    @staticmethod
    def reset_current_user(token: Token) -> None:
        """
        重置当前用户信息

        :param token: 设置用户信息时返回的令牌
        """
        current_user.reset(token)

    @staticmethod
    def clear_all() -> None:
        """
        清除所有请求级上下文变量

        注意：不会清空 current_redis（server 生命周期级别）。
        """
        current_exclude_patterns.set(None)
        current_user.set(None)


class RedisContext:
    """
    Redis 客户端上下文管理（server 生命周期级别）

    应用启动时调用 set_redis() 注入 aioredis 客户端，
    后续任意位置可通过 get_redis() 获取。请求级别的 clear_all() 不会清除 redis。
    """

    @staticmethod
    def set_redis(redis: 'aioredis.Redis') -> Token:
        """
        设置当前可用的 Redis 客户端（应用启动时调用一次）

        :param redis: aioredis 客户端
        :return: 上下文变量令牌，用于重置
        """
        return current_redis.set(redis)

    @staticmethod
    def get_redis() -> 'aioredis.Redis':
        """
        获取当前可用的 Redis 客户端

        :return: aioredis 客户端
        :raises RuntimeError: 未初始化时抛出
        """
        redis = current_redis.get()
        if redis is None:
            raise RuntimeError(
                'Redis 客户端未初始化。请在应用启动时调用 RedisContext.set_redis(redis)。'
            )
        return redis

    @staticmethod
    def try_get_redis() -> 'aioredis.Redis | None':
        """
        尝试获取当前可用的 Redis 客户端（不抛异常）

        :return: aioredis 客户端或 None
        """
        return current_redis.get()

    @staticmethod
    def reset_redis(token: Token) -> None:
        """
        重置 Redis 客户端（一般在应用关闭时调用）

        :param token: set_redis 时返回的令牌
        """
        current_redis.reset(token)

    @staticmethod
    def clear() -> None:
        """
        清空当前 Redis 客户端（应用关闭时调用）
        """
        current_redis.set(None)
