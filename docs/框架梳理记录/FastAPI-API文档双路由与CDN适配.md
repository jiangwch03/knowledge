# FastAPI API 文档双路由与 CDN 适配

项目通过 `APIDocsUtil`（`knowledge_common/utils/server_util.py`）定制 Swagger / ReDoc，解决国内 CDN、网关 `root_path`、直连访问三件事。

## 启动时三步

```python
APIDocsUtil.setup_docs_static_resources()   # ① CDN
app = FastAPI(
    docs_url='/proxy-docs',                 # ② 网关用
    openapi_url='/proxy-openapi.json',
    redoc_url='/proxy-redoc',
)
APIDocsUtil.custom_api_docs_router(app)     # ③ 直连用 /docs
```

| 步骤 | 解决什么 |
|------|----------|
| ① monkey-patch | 文档页 JS/CSS 改走 npmmirror，国内能加载 |
| ② FastAPI 内置 `/proxy-*` | 网关访问；HTML 里的 openapi_url **会带** `root_path` 前缀 |
| ③ 手动注册 `/docs` 等 | 直连后端；openapi_url **硬编码** `/openapi.json`，不带前缀 |

## 为什么要两套路由

配置了 `APP_ROOT_PATH`（如 `/api/knowledge_content`）后，FastAPI 内置文档页会把该前缀拼进 openapi 地址：

- 经网关：前缀正确，能转到后端 `/proxy-openapi.json`
- 直连 `127.0.0.1:9098`：带前缀的路径不存在 → 404

因此不能只注册一套 `/docs`：内置路由服务网关，自定义路由服务直连。

| | 网关 `/proxy-docs` | 直连 `/docs` |
|--|-------------------|--------------|
| 注册方式 | FastAPI 构造参数 | `custom_api_docs_router` |
| openapi_url | 带 `root_path` | `/openapi.json`（无前缀） |

## CDN（步骤①）

`setup_docs_static_resources()` 替换 `fastapi.applications` 里的 `get_swagger_ui_html` / `get_redoc_html`，强制注入 npmmirror 地址。`docs_url` 只管「页面路径」，不管「资源从哪加载」。

## 禁用文档

`APP_DISABLE_SWAGGER` / `APP_DISABLE_REDOC` 为 true 时：内置 `/proxy-*` 不再注册；自定义路由仍挂上对应路径，返回「文档已禁用」提示页，避免裸 404。
