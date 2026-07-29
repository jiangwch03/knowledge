## Why

文档切分与向量化（`knowledge-content`）已就绪，但缺少独立**知识问答读路径**。需求已定稿于 `docs/rag/知识检索/01-需求设计.md`：新建 `knowledge-retrieval`，实现主题路由 →（按需）混合检索 → 单 Agent 流式问答（可按需 Tavily），并配套会话前端；会话/SSE 复用 `knowledge-common` Agent 基座，不 0→1 重写。

## What Changes

- 新建 workspace 包 **`knowledge-retrieval`**（端口默认 `9101`），承载检索与知识问答后端。
- **混合检索**：向量 ANN + `text` 全文/BM25（或等价），RRF 融合；默认 `top_k=5`、`score_threshold=0.5`；`releaseTag`/`taskId` 可传（调试/RAGAS）。
- **父片回填**：父全文替换；`chunkId`（父）+ `hitChunkId`（子）+ `expandedFromChild`。
- **数据权限**：Milvus 冗余 `dept_id`/`user_id`，检索按 data_scope filter；**content 写路径同步写入**。
- **主题字典闸门**：`sys_dict` 维护主题（milvus / ai_production / langchain / langgraph）；图内 `topic_gate` 中间件决定提示词与是否检索。
- **单 Agent 图**：一套 Checkpointer；图内改写 → 路由 → 条件混合检索；Tool 含 Tavily（Key 走 `sys_config` 占位，禁止 SQL 写真实 Key）。
- **会话**：复用 `knowledge_agent_session` / `knowledge_agent_message` + `AgentSessionService` / `AgentChatService`；新 `agent_type`。
- **前端**：`knowledge-web` 新菜单 + 参考爬虫的会话页（本期做）。
- **不做**：图谱、Text2SQL、上传打 topic、流量百分比灰度、BGE 精排、双 Agent 图、embedding 消费者挂在 retrieval。

## Capabilities

### New Capabilities

- `retrieval-service-scaffold`: `knowledge-retrieval` 包与可启动应用（无 embedding 消费者）。
- `knowledge-retrieve`: 混合检索 API + 父片回填 + release/task 过滤 + 向量侧 data_scope。
- `knowledge-qa-agent`: 单 Agent 问答（图内改写/topic 路由、条件检索中间件、Tavily Tool、客服/知识双提示词）。
- `knowledge-qa-web`: 知识问答菜单与会话前端（复用 Agent 会话 API 形态）。

### Modified Capabilities

- `document-embedding`: 向量写入增加 `dept_id`/`user_id`；Milvus DDL 支持权限标量索引与 `text` 全文/BM25（或等价）能力，供混合检索与 ACL。

## Impact

- **新增**：`knowledge-retrieval/`、启动脚本、菜单/权限/字典/参数种子 SQL（Tavily key **空占位**）。
- **修改**：`knowledge-content` upsert 写权限字段；`sql/milvus/manage_document_vector.py`（及存量迁移策略）；`knowledge-web` 问答页；根 workspace。
- **复用**：`knowledge-common` Agent 会话与 SSE runtime、Milvus client、Config/Dict、鉴权。
- **参考需求**：`docs/rag/知识检索/01-需求设计.md`。
