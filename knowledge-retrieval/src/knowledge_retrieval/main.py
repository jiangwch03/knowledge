import uvicorn
from knowledge_common.config.env import AppConfig
from knowledge_retrieval.server.server import create_app


def main():
    uvicorn.run(
        app='knowledge_retrieval.server.server:create_app',
        host=AppConfig.app_host,
        port=AppConfig.app_port,
        root_path=AppConfig.app_root_path,
        reload=AppConfig.app_reload,
        workers=AppConfig.app_workers,
        factory=True,
    )


if __name__ != '__main__':
    app = create_app()

if __name__ == '__main__':
    main()
