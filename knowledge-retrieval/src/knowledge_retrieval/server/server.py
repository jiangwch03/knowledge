import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from knowledge_common.common.constant import LockConstant
from knowledge_common.common.router import auto_register_routers
from knowledge_common.config.env import AppConfig, MessageStreamConfig
from knowledge_common.config.get_db import close_async_engine, init_create_table
from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.redis import RedisConnection
from knowledge_common.config.get_scheduler import SchedulerUtil
from knowledge_common.service.config_service import ConfigService
from knowledge_common.service.dict_service import DictDataService
from knowledge_common.exceptions.handle import handle_exception
from knowledge_common.broadcast import BroadcastService
from knowledge_common.message_stream import MessageStreamService
from knowledge_common.middlewares.handle import handle_middleware
from knowledge_common.sub_applications.handle import handle_sub_applications
from knowledge_common.utils.common_util import worship
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.server_util import APIDocsUtil, IPUtil, StartupUtil
from knowledge_common.utils.transport_crypto_util import TransportKeyProvider
from knowledge_retrieval.common.root_path import CODE_ROOT
from knowledge_retrieval.message.broadcast_test_publisher import RetrievalBroadcastTestPublisher
from knowledge_retrieval.message.test_publisher import RetrievalMessageTestPublisher
from knowledge_common.agent.memory.short_memory.checkpointer import Checkpointer

async def _start_background_tasks(app: FastAPI) -> None:
    """
    启动应用后台任务

    :param app: FastAPI对象
    :return: None
    """
    # 将 app_name 注入到 app.state，供「自产自销」日志隔离使用
    app.state.app_name = AppConfig.app_name
    await SchedulerUtil.init_system_scheduler(app.state.redis, app_scope=app.state.app_name)


async def _init_broadcast(app: FastAPI) -> None:
    """
    初始化消息广播服务（BroadcastService 三步范式）

    基于 Redis Pub/Sub 的 fire-and-forget 广播通道，用于定时任务同步等全局通知场景。
    单连接多路分发，所有 channel 共享一条 pubsub 连接。

    :param app: FastAPI 对象（提取 app.state.redis 作为 Redis 后端连接）
    :return: None
    """
    BroadcastService.init(redis=app.state.redis)
    BroadcastService.register_subscriber_paths([
        'knowledge_retrieval.message.subscriber',
    ])
    await BroadcastService.discover_and_start()
    # 启动自检：发送失败仅打日志，不阻塞启动
    await RetrievalBroadcastTestPublisher.send_demo()


async def _init_message_stream(app: FastAPI) -> None:
    """
    初始化消息流服务（基础设施注册，非后台任务）

    接入范式三步 + 启动自检：
        1. 注入后端实现（按 .env 的 ``MESSAGE_STREAM_BACKEND`` 自动选 Redis/Kafka）
        2. 声明消费者扫描路径（message/consumer 下所有 @consumer 装饰函数）
        3. 扫描 + 拉起后台消费协程
        4. 启动自检：发送一条测试消息验证生产-消费链路通畅

    :param app: FastAPI 对象（提取 app.state.redis 作为 Redis 后端连接；Kafka 后端可忽略）
    :return: None
    """
    MessageStreamService.init_from_settings(MessageStreamConfig, redis=app.state.redis)
    MessageStreamService.register_consumer_paths(['knowledge_retrieval.message.consumer'])
    await MessageStreamService.discover_and_start()
    # 启动自检：发送失败仅打日志，不阻塞启动
    await RetrievalMessageTestPublisher.send_demo()


async def _stop_background_tasks(app: FastAPI) -> None:
    """
    停止应用后台任务并释放资源

    :param app: FastAPI对象
    :return: None
    """
    lock_task = getattr(app.state, 'lock_renewal_task', None)
    if lock_task:
        lock_task.cancel()
        try:
            await lock_task
        except asyncio.CancelledError:
            pass
    await RedisConnection.close_redis_pool(app)
    await SchedulerUtil.close_system_scheduler()
    await close_async_engine()


async def _shutdown_message_stream() -> None:
    """
    关闭消息流服务（取消后台消费协程、关闭后端）

    必须在 Redis 连接池关闭之前调用。

    :return: None
    """
    await MessageStreamService.shutdown()


# 生命周期事件
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    应用生命周期管理

    :param app: FastAPI对象
    :return: None
    """
    # 启动引导日志：在连接任何外部服务之前打印，确保用户第一时间看到启动信息
    logger.info(f'⏰️ {AppConfig.app_name}开始启动')

    #创建 Redis 连接池
    app.state.redis = await RedisConnection.create_redis_pool(log_enabled=False)

    # 获取启动日志锁 多进程模式下 只有抢占到锁的进程打印启动日志
    startup_log_enabled = await StartupUtil.acquire_startup_log_gate(
        redis=app.state.redis,
        lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
        worker_id=SchedulerUtil._worker_id,
        lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
    )
    app.state.startup_log_enabled = startup_log_enabled

    # 获取锁成功后立即启动锁续期任务，避免初始化时间过长导致锁过期
    if startup_log_enabled:
        app.state.lock_renewal_task = StartupUtil.start_lock_renewal(
            redis=app.state.redis,
            lock_key=LockConstant.APP_STARTUP_LOCK_KEY,
            worker_id=SchedulerUtil._worker_id,
            lock_expire_seconds=LockConstant.LOCK_EXPIRE_SECONDS,
            interval_seconds=LockConstant.LOCK_RENEWAL_INTERVAL,
            on_lock_lost=SchedulerUtil.on_lock_lost,
        )

    with logger.contextualize(startup_phase=True, startup_log_enabled=startup_log_enabled):
        if startup_log_enabled:
            worship()

        # 验证传输加密配置
        TransportKeyProvider.validate_runtime_configuration()

        # 初始化数据库表 没表建表 有表跳过 表结构变更跳过
        await init_create_table()

        # 检查 Redis 连接
        await RedisConnection.check_redis_connection(app.state.redis, log_enabled=startup_log_enabled)

        # 应用启动时缓存字典表
        await DictDataService.init_cache(app.state.redis)

        #  应用启动时缓存参数配置表
        await ConfigService.init_cache(app.state.redis)

        # 加载提示词配置（自动发现 src/configs/prompts.yaml）
        prompt_config.load()

        # 启动后台任务（调度器、日志聚合等长运行协程）
        await _start_background_tasks(app)

        # 初始化消息广播服务（BroadcastService）
        await _init_broadcast(app)

        # 初始化消息流服务（基础设施注册，独立于后台任务）
        await _init_message_stream(app)

        # 初始化 LangGraph Redis Checkpointer（依赖 Redis）
        await Checkpointer.init_checkpointer()

    # 启动成功日志打印
    if startup_log_enabled:
        # 短暂等待确保下面的启动日志在最后打印
        await asyncio.sleep(0.5)
        logger.info(f'🚀 {AppConfig.app_name}启动成功')
        host = AppConfig.app_host
        port = AppConfig.app_port
        if host == '0.0.0.0':
            local_ip = IPUtil.get_local_ip()
            network_ips = IPUtil.get_network_ips()
        else:
            local_ip = host
            network_ips = [host]

        app_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}</cyan>']
        app_links.extend(f'📡 Network:  <cyan>http://{ip}:{port}</cyan>' for ip in network_ips)
        logger.opt(colors=True).info('💻 应用地址:\n' + '\n'.join(app_links))

        if not AppConfig.app_disable_swagger:
            swagger_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}{APIDocsUtil.docs_url()}</cyan>']
            swagger_links.extend(
                f'📡 Network:  <cyan>http://{ip}:{port}{APIDocsUtil.docs_url()}</cyan>' for ip in network_ips
            )
            logger.opt(colors=True).info('📄 Swagger文档:\n' + '\n'.join(swagger_links))

        if not AppConfig.app_disable_redoc:
            redoc_links = [f'🏠 Local:    <cyan>http://{local_ip}:{port}{APIDocsUtil.redoc_url()}</cyan>']
            redoc_links.extend(
                f'📡 Network:  <cyan>http://{ip}:{port}{APIDocsUtil.redoc_url()}</cyan>' for ip in network_ips
            )
            logger.opt(colors=True).info('📚 ReDoc文档:\n' + '\n'.join(redoc_links))

    yield

    shutdown_log_enabled = getattr(app.state, 'startup_log_enabled', False)
    with logger.contextualize(startup_phase=True, startup_log_enabled=shutdown_log_enabled):
        # 先关闭消息广播服务（依赖 Redis，须在连接池关闭前）
        await BroadcastService.shutdown()
        # 关闭消息流服务（依赖 Redis，须在连接池关闭前）
        await _shutdown_message_stream()
        await _stop_background_tasks(app)


def create_app() -> FastAPI:
    """
    创建FastAPI应用

    :return: FastAPI对象
    """
    # 配置API文档静态资源
    APIDocsUtil.setup_docs_static_resources()
    # 初始化FastAPI对象
    app = FastAPI(
        title=AppConfig.app_name,  # 应用名称
        description=f'{AppConfig.app_name}接口文档',  # API文档描述信息
        version=AppConfig.app_version,  # 应用版本号
        lifespan=lifespan,  # 生命周期管理（启动/关闭事件）
        openapi_url=APIDocsUtil.proxy_openapi_url(),  # OpenAPI schema地址（支持代理前缀）
        docs_url=APIDocsUtil.proxy_docs_url(),  # Swagger UI文档地址
        redoc_url=APIDocsUtil.proxy_redoc_url(),  # ReDoc文档地址
        swagger_ui_oauth2_redirect_url=APIDocsUtil.proxy_oauth2_redirect_url(),  # OAuth2回调重定向地址
    )

    # 自定义API文档路由，修复无法直接通过后端地址访问文档的问题 fastapi注册了/proxy-docs 这里手动注册/docs
    APIDocsUtil.custom_api_docs_router(app)

    # 挂载子应用  目前不涉及子应用
    """
    FastAPI/Starlette 的 Mount 机制
        1. 挂载静态文件服务
            app.mount("/static", StaticFiles(directory="static"), name="static")
            # 访问 /static/logo.png 就会读取 static/logo.png
        2.挂载另一个 FastAPI 实例
            sub_app = FastAPI()
            app.mount("/sub", sub_app)
            # 子应用的路由 /users 变成 /sub/users
        3. 挂载 Swagger/ReDoc 等静态资源(前端页面) 
    """
    handle_sub_applications(app)

    # 加载中间件处理方法
    handle_middleware(app)

    # 加载全局异常处理方法
    handle_exception(app)

    # 自动注册路由
    auto_register_routers(app,CODE_ROOT)

    return app
