# FastAPI Swagger UI 文档机制全景

## 概述

本项目为 FastAPI 的 API 文档（Swagger UI / ReDoc）实现了一套完整的自定义方案，解决三个核心问题：

| 问题 | 解决方案 | 详细文档 |
|------|---------|---------|
| 国内无法加载默认 CDN 的 JS/CSS | Monkey-patch 替换静态资源地址 | [静态资源配置说明](fastapi-docs-static-resources.md) |
| FastAPI 内置路由受 root_path 影响，直连后端 404 | 注册独立的 /docs 路由 | [custom_api_docs_router 机制说明](fastapi-custom-api-docs-router.md) |
| 为什么 FastAPI 构造参数用 /proxy-docs 而不是 /docs | 避免 root_path 干扰 + 防止路由冲突 | [/proxy-docs 设计说明](fastapi-proxy-docs-design.md) |

## 执行流程

```python
def create_app() -> FastAPI:
    # ① 替换静态资源 CDN 地址（monkey-patch）
    APIDocsUtil.setup_docs_static_resources()

    # ② 创建 FastAPI 实例，注册 /proxy-* 系列路由（网关访问用）
    app = FastAPI(
        openapi_url='/proxy-openapi.json',
        docs_url='/proxy-docs',
        redoc_url='/proxy-redoc',
    )

    # ③ 手动注册 /docs、/openapi.json 等路由（直连访问用）
    APIDocsUtil.custom_api_docs_router(app)
```

三步之间的关系：

```
步骤①  setup_docs_static_resources()
  │     解决「页面能不能正常渲染」
  │     影响范围：所有文档页面（/proxy-docs 和 /docs 都受益）
  │
步骤②  FastAPI(docs_url='/proxy-docs', ...)
  │     解决「通过网关能不能访问文档」
  │     注册路由：/proxy-docs, /proxy-openapi.json, /proxy-redoc
  │
步骤③  custom_api_docs_router(app)
        解决「直连后端能不能访问文档」
        注册路由：/docs, /openapi.json, /redoc
```

## 两套路由对比

| | 网关访问（/proxy-*） | 直连访问（/docs） |
|--|-------------------|-----------------|
| **注册方式** | FastAPI 内置 | 手动 add_route |
| **openapi_url** | 受 root_path 影响，带前缀 | 硬编码 `/openapi.json`，无前缀 |
| **静态资源 CDN** | npmmirror（monkey-patch 生效） | npmmirror（直接传参） |
| **访问地址** | `gateway/api/knowledge_content/proxy-docs` | `127.0.0.1:9098/docs` |

## 禁用文档时的行为

当 `APP_DISABLE_SWAGGER = true` 时：
- FastAPI 内置不注册 `/proxy-docs`（`docs_url=None`）
- `custom_api_docs_router` 接管所有路由，统一返回"文档已禁用"提示页面
- 详见 → [custom_api_docs_router 条件注册逻辑](fastapi-custom-api-docs-router.md#_register_docs_routes-条件注册逻辑)

## 相关文档索引

- [fastapi-docs-static-resources.md](fastapi-docs-static-resources.md) — CDN 替换原理、monkey-patch 流程、与 docs_url 的差异对比
- [fastapi-custom-api-docs-router.md](fastapi-custom-api-docs-router.md) — 自定义路由注册逻辑、启用/禁用条件分支、与内置机制的协作
- [fastapi-proxy-docs-design.md](fastapi-proxy-docs-design.md) — 为什么用 /proxy-docs、root_path 的影响、与 Spring Boot context-path 的差异
