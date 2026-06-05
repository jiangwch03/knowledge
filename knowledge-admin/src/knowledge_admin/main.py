import uvicorn
from knowledge_common.config.env import AppConfig

from knowledge_admin.server.server import create_app


def main() -> None:
    uvicorn.run(
        app='knowledge_admin.server.server:create_app',  # ASGI应用的导入路径，格式为 "模块路径:工厂函数名"
        host=AppConfig.app_host,  # 服务监听的主机地址
        port=AppConfig.app_port,  # 服务监听的端口号
        root_path=AppConfig.app_root_path,  # 应用的根路径前缀，用于反向代理场景
        reload=AppConfig.app_reload,  # 是否启用热重载，代码变更时自动重启服务
        workers=AppConfig.app_workers,  # 工作进程数，用于多进程部署 多进程不支持reload=true
        factory=True,  # 标记app参数为工厂函数，uvicorn会调用该函数创建应用实例
    )

if __name__ != '__main__':
    app = create_app()

if __name__ == '__main__':
    main()
