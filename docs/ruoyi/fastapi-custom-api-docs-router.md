# custom_api_docs_router 自定义文档路由机制说明

## 作用

`APIDocsUtil.custom_api_docs_router(app)` 的核心目的是**让直连后端时也能正常访问 API 文档**。

## 为什么需要它

FastAPI 内置的 `/proxy-docs` 路由受 `root_path` 影响，生成的 HTML 中 openapi_url 带有网关前缀（如 `/api/knowledge_rag/proxy-openapi.json`），直连后端时该路径不存在导致 404。

`custom_api_docs_router` 手动注册 `/docs` 路由，硬编码 `openapi_url='/openapi.json'`（不受 root_path 影响），解决直连场景。

## 注册逻辑

```python
def custom_api_docs_router(cls, app):
    # 1. 定义 4 个自定义路由处理函数
    custom_openapi             # 返回 OpenAPI JSON schema
    custom_swagger             # 返回 Swagger UI HTML（openapi_url='/openapi.json'）
    custom_swagger_ui_redirect # 返回 OAuth2 重定向页面
    custom_redoc               # 返回 ReDoc HTML

    # 2. 注册 /openapi.json 路由
    app.add_route('/openapi.json', custom_openapi)

    # 3. 根据启用/禁用状态注册文档页面路由
    _register_docs_routes(app, custom_swagger, custom_swagger_ui_redirect, custom_redoc)
```

## `_register_docs_routes` 条件注册逻辑

### Swagger 启用时（`APP_DISABLE_SWAGGER = false`）

```
注册路由:
  /docs                 → 正常 Swagger UI HTML
  /docs/oauth2-redirect → OAuth2 重定向页面
```

此时 `/proxy-docs` 已由 FastAPI 内置机制处理，无需重复注册。

### Swagger 禁用时（`APP_DISABLE_SWAGGER = true`）

```
注册路由:
  /docs                       → "文档已禁用" 提示页面
  /proxy-docs                 → "文档已禁用" 提示页面
  /docs/oauth2-redirect       → "文档已禁用" 提示页面
  /proxy-docs/oauth2-redirect → "文档已禁用" 提示页面
```

禁用时 FastAPI 内置不再注册 `/proxy-docs`（因为 `docs_url=None`），所以自定义路由需要接管，返回友好的禁用提示而非 404。

### ReDoc 同理

```
启用: 注册 /redoc
禁用: 注册 /redoc + /proxy-redoc（都返回禁用提示）
```

## 禁用判断位置

处理函数内部通过配置决定返回内容：

```python
async def _custom_swagger(...):
    if not AppConfig.app_disable_swagger:
        return get_swagger_ui_html(...)       # 正常文档
    return cls._get_disabled_html_content(...) # "已禁用" 提示页

async def _custom_redoc(...):
    if not AppConfig.app_disable_redoc:
        return get_redoc_html(...)            # 正常文档
    return cls._get_disabled_html_content(...) # "已禁用" 提示页
```

## 与 FastAPI 内置机制的协作关系

```
FastAPI 构造参数                    custom_api_docs_router
─────────────────                  ─────────────────────
docs_url='/proxy-docs'        +    手动注册 /docs
openapi_url='/proxy-openapi.json'  手动注册 /openapi.json
redoc_url='/proxy-redoc'      +    手动注册 /redoc

        ↓                                  ↓
   适用网关访问                         适用直连访问
（openapi_url 带 root_path）      （openapi_url 无前缀）
```
