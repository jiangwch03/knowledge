# 知识库发布评测 — 运维说明

## 发布入口

- **已移除** embedding 自动 promote（`auto_promote_completed_canary` / `embedding_auto_publish_job`）。
- **唯一发布入口**：`knowledge-admin` 测评任务「发布」接口  
  `POST /rag/eval/task/{evalTaskId}/publish`  
  要求：任务 `OPEN` 且历史上 ≥1 次 `SUCCESS` run → 调 content `POST /internal/embedding/promote` → 成功后任务 `ARCHIVED`。
- **不做** content 侧运营手动 promote UI；content 仅保留评测编排用的 internal facade。

## 存量 canary

向量化完成后停在 canary，需走：测评集生成 →（人工改题）→ 创建测评任务绑定 canary embedding 任务 → 跑测评 SUCCESS → 点发布。

## 跨服务调用

- 协议仍是 **HTTP + httpx**（JSON facade），不是 gRPC。
- **服务发现**：开启 Nacos 后，admin 按服务名发现 content / retrieval 实例；失败回退静态 URL。

### Nacos（默认关闭）

```bash
NACOS_ENABLED=true
NACOS_SERVER_ADDR=127.0.0.1:8848
NACOS_NAMESPACE=
NACOS_GROUP=DEFAULT_GROUP
NACOS_USERNAME=
NACOS_PASSWORD=
# 可选：显式注册 IP；空则自动取本机网卡
NACOS_REGISTER_IP=
```

服务名默认取各服务 `APP_NAME`（`knowledge-content` / `knowledge-retrieval` / `knowledge-admin`）。  
admin 发现用：

```bash
KNOWLEDGE_CONTENT_SERVICE_NAME=knowledge-content
KNOWLEDGE_RETRIEVAL_SERVICE_NAME=knowledge-retrieval
# 本地调试直连（非空则绕过 Nacos，类比 @FeignClient(url=...)）；生产勿配
# KNOWLEDGE_CONTENT_URL=http://127.0.0.1:9098
# KNOWLEDGE_RETRIEVAL_URL=http://127.0.0.1:9101
```

## 跨服务鉴权

请求入口自动注入 `Authorization`（`ServiceAuthContext`）；RPC Client / ServiceHttp 自动带头。后台 `asyncio.create_task` 继承当时 ContextVar。

## 配置

`RpcClientConfig`：

- `knowledge_content_service_name` / `knowledge_content_root_path` / `knowledge_content_url`（url 非空则直连绕过 Nacos）
- `knowledge_retrieval_service_name` / `knowledge_retrieval_root_path` / `knowledge_retrieval_url`
- `knowledge_eval_judge_model`：出题/裁判适配 `param_id`（空则回退 `knowledge_qa_agent`）

## Ragas POC（Python 3.13）

- 已加入依赖 `ragas==0.4.3`（随 `uv add` 解析）。
- **现状**：在当前仓库的 `langchain-community==0.4.2` 下 `import ragas` 会因
  `langchain_community.chat_models.vertexai` 缺失而失败。
- **运行时**：`EvalTaskService._score_item` try/except，失败则写入占位指标（`note` 说明原因），
  **不阻断** SUCCESS run 落库与人工发布。
- **后续**：升级/对齐 ragas 与 langchain 生态，或改用 ragas 新 LLM factory 绕开 community vertexai 导入。
