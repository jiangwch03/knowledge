from starlette.types import ASGIApp, Receive, Scope, Send

from knowledge_common.common.context import RedisContext


class RedisContextMiddleware:
    """
    Redis 上下文注入中间件（pure ASGI 风格）

    问题背景：
        RedisContext 基于 ContextVar 存储 redis 客户端，ContextVar.set() 仅对当前
        asyncio task 可见。uvicorn 启动时 RedisContext.set_redis() 是在 lifespan task
        中调用的，但 HTTP 请求处理是 uvicorn 主 task 派生的 handler task，handler task
        不会自动继承 lifespan task 的 context，导致 HTTP 请求处理路径中调用
        RedisContext.get_redis() 抛 RuntimeError("Redis 客户端未初始化")。

    解决方案：
        在 HTTP 请求入口（pure ASGI __call__）将 app.state.redis 注入到当前 task 的
        context 中，使该 task 内所有后续代码（包括 SchedulerUtil.broadcast_* →
        RedisPubSub.publish → RedisContext.get_redis）都能拿到 redis。

    为什么用 pure ASGI 而不是 BaseHTTPMiddleware：
        BaseHTTPMiddleware 内部用 anyio.create_task_group() 派生新 task 跑下游 app，
        会丢失 ContextVar 传递。pure ASGI 中间件的 __call__ 中所有 await 都在同一个
        task 中执行，set_redis() 后下游路由 handler 才能拿到。

    说明：
        - 当前 task 结束（HTTP 请求完成）后 context 自动销毁，无需手动 reset
        - 多 worker 场景下每个 worker 独立注入自己的 redis 客户端（process 级隔离）
        - 仅在 redis 已初始化（lifespan 完成后）才注入，避免覆盖
        - 当前 task 派生出的子 task（如 SchedulerUtil.broadcast_xxx 内部 create_task）
          会自动继承此 context，链路完整

    fastapi-example:
        >>> app = FastAPI()
        >>> app.add_middleware(RedisContextMiddleware)
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        # FastAPI/Starlette 会在 scope 中放入 app 引用，通过它能拿到 app.state.redis
        app = scope.get('app')
        if app is not None:
            redis = getattr(app.state, 'redis', None)
            if redis is not None:
                RedisContext.set_redis(redis)

        await self.app(scope, receive, send)


def add_redis_context_middleware(app: ASGIApp) -> None:
    """
    添加 Redis 上下文注入中间件

    :param app: FastAPI对象
    """
    app.add_middleware(RedisContextMiddleware)
