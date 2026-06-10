from fastapi import FastAPI

from knowledge_common.common.transactional import SessionContextMiddleware
from knowledge_common.config.env import AppConfig
from knowledge_common.middlewares.api_response_header_middleware import add_api_response_header_middleware
from knowledge_common.middlewares.context_middleware import add_context_cleanup_middleware
from knowledge_common.middlewares.cors_middleware import add_cors_middleware
from knowledge_common.middlewares.demo_mode_middleware import add_demo_mode_middleware
from knowledge_common.middlewares.gzip_middleware import add_gzip_middleware
from knowledge_common.middlewares.redis_context_middleware import add_redis_context_middleware
from knowledge_common.middlewares.trace_middleware import add_trace_middleware
from knowledge_common.middlewares.transport_crypto_middleware import add_transport_crypto_middleware


def handle_middleware(app: FastAPI) -> None:
    """
    全局中间件处理
    """
    # 加载session上下文中间件（为get_current_session()提供请求级session）
    app.add_middleware(SessionContextMiddleware)
    # 加载Redis上下文注入中间件（为HTTP请求处理路径的RedisContext.get_redis()提供redis）
    add_redis_context_middleware(app)
    # 加载上下文清理中间件
    add_context_cleanup_middleware(app)
    # 加载跨域中间件
    add_cors_middleware(app)
    # 加载gzip压缩中间件
    add_gzip_middleware(app)
    # 加载接口响应头追加中间件
    add_api_response_header_middleware(app)
    # 加载trace中间件
    add_trace_middleware(app)
    if AppConfig.app_demo_mode:
        # 加载演示模式中间件
        add_demo_mode_middleware(app)
    # 加载传输层请求解密/响应加密中间件
    add_transport_crypto_middleware(app)
