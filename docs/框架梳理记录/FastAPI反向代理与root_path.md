# FastAPI 反向代理场景下的路由前缀处理

## 1. 问题背景

当 FastAPI 应用部署在反向代理（网关/Nginx）之后时，外部访问路径通常带有代理前缀，例如：

```
https://gateway.example.com/api/knowledge_content/users
```

而应用内部注册的路由是裸路径：

```python
@router.get("/users")
async def list_users():
    ...
```

这就产生了一个问题：**代理前缀由谁负责处理？**

## 2. 核心机制：`root_path`

本项目通过 `uvicorn.run(root_path=...)` 参数解决该问题，核心机制分为三层：

### 2.1 Uvicorn 层 —— 记录前缀

```python
# src/main.py
uvicorn.run(
    app='knowledge_content.server.server:create_app',
    root_path=AppConfig.app_root_path,  # '/api/knowledge_content'
    factory=True,
)
```

Uvicorn 将 `root_path` 写入每个 ASGI 请求的 `scope['root_path']` 中。

### 2.2 Starlette 层 —— 剥离前缀

FastAPI 底层依赖 Starlette 的路由器。Starlette 在匹配路由时，自动从请求路径中剥离 `root_path`：

```
scope['path']      = '/api/knowledge_content/users'
scope['root_path'] = '/api/knowledge_content'
实际匹配路径      = '/users'
```

### 2.3 FastAPI 层 —— 无额外逻辑

FastAPI 本身不处理前缀剥离，完全依赖 Starlette 的机制。业务代码无需感知代理前缀。

## 3. 网关配置要点

### 3.1 关键原则：网关应完整透传路径

网关**不应**去掉前缀，而应把完整路径转发给后端，由 FastAPI 内部处理。

### 3.2 Nginx 配置陷阱

Nginx 的 `proxy_pass` 末尾斜杠行为容易踩坑：

```nginx
# ❌ 错误：会去掉 /api/knowledge_content/ 前缀
location /api/knowledge_content/ {
    proxy_pass http://backend:8080/;
}
# 后端收到 /users，但 root_path 仍是 /api/knowledge_content → 404

# ✅ 正确：保留完整路径
location /api/knowledge_content/ {
    proxy_pass http://backend:8080;
}
# 后端收到 /api/knowledge_content/users，root_path 剥离后匹配 /users
```

## 4. 项目中的代码体现

### 4.1 应用入口配置

```python
# src/main.py
uvicorn.run(
    app='knowledge_content.server.server:create_app',
    root_path=AppConfig.app_root_path,  # 从 .env.dev 读取 '/api/knowledge_content'
    factory=True,
)
```

### 4.2 环境变量配置

```bash
# .env.dev
APP_ROOT_PATH = '/api/knowledge_content'
```

### 4.3 文档路由的特殊处理

API 文档（Swagger/ReDoc）需要生成正确的 URL，因此项目中单独处理了代理前缀：

```python
# src/knowledge_content/server/server.py
app = FastAPI(
    openapi_url=APIDocsUtil.proxy_openapi_url(),   # 带代理前缀的 openapi.json 路径
    docs_url=APIDocsUtil.proxy_docs_url(),         # 带代理前缀的 Swagger UI 路径
    redoc_url=APIDocsUtil.proxy_redoc_url(),       # 带代理前缀的 ReDoc 路径
    swagger_ui_oauth2_redirect_url=APIDocsUtil.proxy_oauth2_redirect_url(),
)

# 同时注册一套裸路径文档路由，支持直接访问后端地址
APIDocsUtil.custom_api_docs_router(app)
```

## 5. 职责分工总结

| 组件 | 职责 |
|------|------|
| **网关（Nginx/Kong/APISIX）** | 完整透传请求路径，**不要**去掉前缀 |
| **Uvicorn** | 通过 `root_path` 参数记录前缀到 ASGI scope |
| **Starlette** | 路由匹配时自动剥离 `root_path` |
| **FastAPI** | 无额外逻辑，依赖 Starlette |
| **业务代码** | 注册裸路由（如 `/users`），不感知代理前缀 |

## 6. 常见问题排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 直接访问后端地址正常，走网关 404 | 网关去掉了前缀 | 检查 `proxy_pass` 末尾是否有斜杠 |
| 文档页面加载但接口请求失败 | `openapi_url` 未适配代理前缀 | 使用 `APIDocsUtil.proxy_openapi_url()` |
| 重定向 URL 错误 | `root_path` 未设置或网关未透传头部 | 确认 `uvicorn.run(root_path=...)` 生效 |

## 7. 补充：自动推断 root_path

如果网关支持发送 `X-Forwarded-Prefix` 头部，Uvicorn 可以自动推断 `root_path`，无需硬编码：

```nginx
proxy_set_header X-Forwarded-Prefix /api/knowledge_content;
```

此时可以省略 `uvicorn.run(root_path=...)` 参数。但显式配置更可控，推荐保留当前方式。
