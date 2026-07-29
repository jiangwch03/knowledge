# knowledge-retrieval

知识检索 / 知识问答服务（默认端口 **9101**）。

## 启动

```bash
# 建议先在仓库根目录完成 workspace sync
uv sync --default-index pypi   # 若本地 Nexus 不可用

./scripts/start-retrieval.sh
# 或
uv run --package knowledge-retrieval python -m knowledge_retrieval.main
```

## 主要接口

- `POST /retrieval/search` — 混合检索（权限 `rag:retrieve:query`）
- `/qa/session/*` — 会话 CRUD（复用 `AgentSessionService`）
- `/qa/chat/*` — 模型列表 / SSE 消息 / 历史消息（权限 `rag:retrieve:chat`）

## 依赖种子

- SQL：`sql/upgrade_knowledge_retrieval.sql`
- Milvus：`sql/milvus/manage_document_vector.py` + `MIGRATION_ACL_BM25.md`
- 冒烟：`docs/rag/知识检索/02-冒烟清单.md`

## 约束

- lifespan **不**注册 embedding 消费者
- 不新增 QA MQ 消费者 / 定时任务
- Tavily Key 仅通过 `sys_config.rag.tavily.api_key` 配置，种子为空占位
