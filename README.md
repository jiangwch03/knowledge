# knowledge
企业知识库RAG系统

## 许可证

本项目基于 [RuoYi-Vue3-FastAPI](https://github.com/insistence/RuoYi-Vue3-FastAPI) 开发，遵循 MIT License。
Copyright (c) 2024 insistence


## FastAPI Swagger UI 文档机制全景(RuoYi-Vue3-FastAPI已实现)
create_app() 针对 Swagger UI 的访问和构建做了自定义方案处理：

| 问题 | 解决方案 |
|------|---------|
| 国内无法加载默认 CDN 的 JS/CSS | Monkey-patch 替换静态资源地址 |
| FastAPI 内置路由受 root_path 影响，直连后端 404 | 注册独立的 /docs 路由 |
| 为什么 FastAPI 构造参数用 /proxy-docs 而不是 /docs | 避免 root_path 干扰 + 防止路由冲突 |

详细方案说明：[FastAPI Swagger UI 文档机制全景](./docs/ruoyi/fastapi-swagger-ui-overview.md)

## FastAPI 多进程
详细说明：[FastAPI 多进程](./docs/fastapi/fastapi-multiprocess.md)

## FastAPI 反向代理场景下的路由前缀处理
详细说明：[FastAPI 多进程](./docs/fastapi/fastapi-root-path-proxy.md)