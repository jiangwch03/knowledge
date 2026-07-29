## Context

需求定稿：`docs/rag/知识检索/01-需求设计.md`。写路径在 `knowledge-content`；读路径与知识问答落在新建 `knowledge-retrieval`。会话/SSE 复用 common Agent 基座（对齐网页爬虫用法），本包只扩展业务图、检索服务与 Tool。

## Goals / Non-Goals

**Goals:**

1. `knowledge-retrieval` 服务（`9101`）：混合检索 API + 知识问答 Agent（多轮会话）。
2. 单 Agent 图内中间件：`query_rewrite` → `topic_gate`（字典主题）→ 条件 `hybrid_retrieve`；Tavily 按需 Tool。
3. Milvus：`dept_id`/`user_id` + `text` 全文能力；content 写入对齐。
4. `knowledge-web` 本期会话页；复用 `AgentSessionService` / `AgentChatService`。

**Non-Goals:**

- 知识图谱 / Neo4j / Text2SQL / 上传打 topic / 流量百分比灰度 / BGE 交叉精排。
- 双 Agent 图切换；deepagents 多 Worker / HITL（一期）。
- retrieval 进程挂 embedding 消费者；真实 Tavily Key 写入仓库或初始化 SQL。

## Decisions

### 1. 独立包 `knowledge-retrieval`

与 content 同级；默认端口 `9101`。lifespan：Redis/DB/字典/参数/鉴权/按需 Checkpointer；**不**注册 embedding 消费者。

### 2. 混合检索（L1）

```
query → embed ──► 向量 ANN (+ release_tag / task_id / data_scope)
     → 关键词 ──► text 全文/BM25（同 filter）
              ↓
           RRF 融合 → score 门槛(默认 0.5) → TopK(默认 5)
              ↓
           父片回填：text=父；chunkId=父；hitChunkId=子；expandedFromChild
```

- 关键词失败 → 降级纯向量。
- 对外 `score` 越大越相关。
- `POST /retrieval/search` 供评测/调试；聊天路径经中间件调用同一 `RetrieveService`。

### 3. 数据权限

- Milvus 冗余 `dept_id`、`user_id`（上传用户）；标量索引。
- 检索 filter 对齐上传/爬取 data_scope 语义。
- content embedding upsert **必须**写入上述字段；存量回填或重嵌（技术方案定迁移）。

### 4. 主题路由 + 单 Agent 图（M）

```
消息 → 单一 qa_agent 图
         middleware（顺序）:
           1) query_rewrite → search_query
           2) topic_gate → prompt_profile + need_retrieve
           3) need_retrieve 时 hybrid_retrieve（custom stream 推 citations）
           4) qa_prompt（cs | knowledge）
         tools: tavily_search
```

- 同一 `agent_type` + 同一 `thread_id`（会话 id），无双图 Checkpointer 冲突。
- 每轮 `build_chat_input` 清空 search_query / gate / retrieve_*，避免 checkpointer 复用上轮路由。
- 不相关：不检索 + 客服提示词（可 Tavily）；禁止伪造知识库 citation。
- 相关：中间件混合检索 + 知识问答提示词（可 Tavily）；网页来源与知识库引用区分。

### 5. Tavily

- Agent Tool，模型决定是否调用。
- Key：`sys_config` 键 `rag.tavily.api_key`；初始化 **空/占位**，管理员自行填写；禁止真实 Key 进 SQL/仓库。

### 6. 会话与 API（复用基座）

- 表：`knowledge_agent_session` / `knowledge_agent_message`。
- Service：`AgentSessionService`、继承 `AgentChatService`；薄 Controller。
- 接口形态对齐 crawler（list/create/rename/close/delete、models、message SSE、messages）。
- 一期可不做 crawler 的 `resume` / `list-all`（无 HITL）。
- **0 定时任务、0 新消费者**（retrieval 侧）。

### 7. 前端

- 新菜单 + 会话页，参考爬虫聊天；调 retrieval API。
- Admin `/ai/chat` 保留为非知识库对话。

### 8. 主题字典

- 字典类型（如 `rag_retrieve_topic`）：`milvus` / `ai_production` / `langchain` / `langgraph`。
- 不改上传/爬取打标。

## Risks / Trade-offs

- **[Risk] Milvus 全文 DDL/重建** → 迁移脚本与停机窗口写清；失败可降级纯向量。
- **[Risk] data_scope 与向量字段不一致（旧数据）** → 强制回填/重嵌策略。
- **[Risk] 主题字典与库内实际语料不一致** → 接受人工维护字典（已拍板）。
- **[Risk] Tavily 费用/延迟** → 默认少条数；失败降级。
- **[Risk] 路由 LLM 误判** → 日志打 related/topics；可后续加人工反馈。

## Migration Plan

1. Workspace 骨架 + 启动脚本。
2. Milvus DDL（权限字段 + text 全文）+ content 写入改造 + 存量策略。
3. RetrieveService + search API。
4. topic_gate + 单 Agent 图 + Tavily + 会话 API。
5. 字典/参数/菜单权限种子；web 会话页。
6. Rollback：停 retrieval 进程；向量 schema 变更需单独回滚方案。

## Open Questions

（需求已收口；实现期仅剩技术选型细节）

1. Milvus 全文具体用 BM25 字段还是稀疏向量 —— 实现时按当前 pymilvus 版本选定。
2. 关键词抽取用规则分词还是轻量模型 —— 优先规则，失败降级。
