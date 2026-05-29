# FastAPI 注册 /proxy-docs 而非 /docs 的设计说明

## 背景

在 `create_app()` 中，FastAPI 构造参数传入的是 `/proxy-docs` 而不是 `/docs`：

```python
app = FastAPI(
    docs_url=APIDocsUtil.proxy_docs_url(),   # → '/proxy-docs'
    openapi_url=APIDocsUtil.proxy_openapi_url(),  # → '/proxy-openapi.json'
)
```

## 原因：`root_path` 会影响 FastAPI 内置文档路由的 openapi_url

项目配置了 `APP_ROOT_PATH = '/api/knowledge_rag'`（传给 uvicorn 的 `root_path`）。

FastAPI 内置文档路由生成 Swagger UI HTML 时，会**自动将 `root_path` 拼接到 `openapi_url` 前面**：

```html
<!-- FastAPI 内置 /proxy-docs 生成的 HTML -->
<script>
  SwaggerUIBundle({ url: "/api/knowledge_rag/proxy-openapi.json" })
</script>
```

这意味着：
- **通过网关访问**：浏览器请求 `gateway/api/knowledge_rag/proxy-openapi.json` → 网关去掉前缀 → 转发到后端 `/proxy-openapi.json` ✅
- **直连后端访问**：浏览器请求 `127.0.0.1:9098/api/knowledge_rag/proxy-openapi.json` → 后端没有这个路径 ❌ 404

## 为什么不能直接注册 /docs

如果把 `docs_url='/docs'` 传给 FastAPI：
- 生成的 HTML 中 openapi_url 会变成 `/api/knowledge_rag/openapi.json`
- 直连后端时同样会 404
- 而且还会与后续 `custom_api_docs_router` 手动注册的 `/docs` 路由冲突

## 设计结论

| 路由 | 注册方式 | openapi_url | 适用场景 |
|------|---------|-------------|---------|
| `/proxy-docs` | FastAPI 内置（`docs_url` 参数） | 带 root_path 前缀 | 通过网关访问 |
| `/docs` | `custom_api_docs_router` 手动注册 | `/openapi.json`（硬编码，无前缀） | 直连后端访问 |

两者分开注册，互不干扰，分别服务不同的访问场景。

## 与 Spring Boot 的差异

Spring Boot 的 `context-path` 会让路由本身带上前缀，直连和网关访问路径一致，不需要拆分两套。
FastAPI 的 `root_path` 只是元数据声明，路由本身不带前缀，路径剥离由网关负责，因此需要两套文档路由来适配两种访问方式。
