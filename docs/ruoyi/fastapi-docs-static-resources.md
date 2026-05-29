# FastAPI 文档静态资源配置说明

## 1. 注入自定义 CDN 地址逻辑

`APIDocsUtil.setup_docs_static_resources()` 通过 **monkey-patch** 机制替换 FastAPI 内部的 `applications.get_swagger_ui_html` 和 `applications.get_redoc_html` 函数，使其在生成文档 HTML 时注入自定义的静态资源 CDN 地址（npmmirror 国内镜像）。

**执行流程：**

```
setup_docs_static_resources()
    │
    ├── 定义 swagger_ui_monkey_patch()
    │       └── 调用原始 get_swagger_ui_html()，但强制注入自定义 JS/CSS URL
    │
    ├── 定义 redoc_monkey_patch()
    │       └── 调用原始 get_redoc_html()，但强制注入自定义 JS URL
    │
    └── 替换 fastapi.applications 模块中的函数引用
            ├── applications.get_swagger_ui_html = swagger_ui_monkey_patch
            └── applications.get_redoc_html = redoc_monkey_patch
```

**替换后的 CDN 地址：**

| 资源 | 默认地址（jsdelivr） | 替换后地址（npmmirror） |
|------|---------------------|----------------------|
| Swagger JS | `cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js` | `registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui-bundle.js` |
| Swagger CSS | `cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css` | `registry.npmmirror.com/swagger-ui-dist/5/files/swagger-ui.css` |
| ReDoc JS | `cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js` | `registry.npmmirror.com/redoc/2/files/bundles/redoc.standalone.js` |

## 2. FastAPI 构造参数 vs setup_docs_static_resources 差异对比

```python
# ① 控制文档页面的「访问路径」—— FastAPI 构造参数
app = FastAPI(
    openapi_url=APIDocsUtil.proxy_openapi_url(),  # → /proxy-openapi.json
    docs_url=APIDocsUtil.proxy_docs_url(),        # → /proxy-docs
    redoc_url=APIDocsUtil.proxy_redoc_url(),      # → /proxy-redoc
)

# ② 控制文档页面内「静态资源加载地址」—— monkey-patch
APIDocsUtil.setup_docs_static_resources()
```

| 对比维度 | FastAPI 构造参数 (`docs_url` 等) | `setup_docs_static_resources()` |
|---------|-------------------------------|-------------------------------|
| **解决的问题** | 文档页面通过什么 URL 路径访问 | 文档页面内的 JS/CSS 从哪个 CDN 加载 |
| **作用层面** | 路由注册（URL path） | HTML 页面内容（资源引用地址） |
| **实现方式** | FastAPI 原生支持的参数配置 | Monkey-patch 替换内部函数 |
| **为什么需要** | 支持反向代理场景下的路径前缀 | FastAPI 未提供 CDN 自定义参数，国内网络无法访问默认 CDN |
| **不配置的后果** | 文档路径不正确，代理转发后 404 | 页面能打开但 JS/CSS 加载失败，Swagger UI 无法渲染 |

**一句话总结：** `docs_url` 决定「能不能找到文档页面」，`setup_docs_static_resources()` 决定「文档页面能不能正常渲染」。
