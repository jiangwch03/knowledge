## Context

知识库向量化写入 Milvus canary 后，现有 `EmbeddingPublishService.auto_promote_completed_canary` 定时自动 promote 到 prod。独立检索已支持 `releaseTag`/`taskId`，但问答 Agent 未透传，始终打 prod。`knowledge-admin` 目前是 RuoYi 风格系统管理，facade 为空壳；仓库无 MCP/Ragas。方案定稿见 `docs/rag/知识库发布评测方案.md`。

## Goals / Non-Goals

**Goals:**

- 离线 Ragas 评测 + 人工决策后，经 admin 测评任务唯一入口发布 canary→prod。
- 按文档维护可复用测评集；生成 Agent + 分段 MCP 一次出题，人工改题。
- 删除 auto-promote；评测采数走 canary + embedding `task_id`。
- 评测表同库存 `knowledge_eval_*`，admin 主责编排。

**Non-Goals:**

- A/B、Langfuse、指标自动门控发布。
- content 独立手动 promote、无测评旁路上 prod。
- 手写录入题目、增量补题 / 再跑生成追加。
- 新开评测微服务。

## Decisions

### D1. 主责放 knowledge-admin

- **选择**：测评集/生成 Agent/任务/run/Ragas/发布编排均在 admin；RPC 调 content、retrieval。
- **理由**：属运营/测试阶段能力，后续监控也倾向后台；横切两服务但以编排为主。
- **备选**：新服务 — 运维成本高；挂 content — 与发布实现耦合过紧。

### D2. 发布入口与门槛

- **选择**：唯一入口 = 测评任务「发布」；删除 auto-promote 与 content 手动 promote UI；历史上 ≥1 次 SUCCESS run 即可发（换集不失效）。
- **理由**：强制「先有测评流程」；门槛简单（A1），不因换集卡死紧急发布。
- **代价**：换集后可不重跑就发，靠人自觉。

### D3. 出题只走生成 Agent 一轮

- **选择**：新建测集 = 选 doc + 名称 → Agent 跑一轮；人工只改；无录入、无补题。
- **配额**：提示词写死总量 20～40，简单:中等:高难 = 1:2:1；少题时尽量保比例。
- **理由**：保证题有原文依据与 used_chunk_ids；控制一期范围。

### D4. 分段 MCP 挂 content

- **选择**：`list_document_segments` / `get_document_segments` / `search_document_segments` 数据与工具挂 content；admin Agent 调 MCP；可与 HTTP/RPC 共用实现。
- **理由**：分段权威数据在 content；禁止默认全量塞上下文。

### D5. Ragas 在 admin 异步跑批

- **选择**：admin 后台任务逐题调 retrieval 非流式评测接口采 `{answer, contexts}`，再算 Ragas 落库；不堵在 retrieval 请求里。
- **指标**（仅人看，不门控）：context_recall/precision/relevancy、faithfulness、answer_relevancy/correctness。

### D6. 数据模型

五张表：`knowledge_eval_dataset`、`dataset_item`、`task`、`run`、`run_item`。task 逻辑关联 `embedding_task_id`（无强外键）。run/run_item 只插入（status 至终态除外）；题目快照防测集漂移。

### D7. retrieval 改造范围

- Agent 与 hybrid retrieve 透传 `releaseTag`（默认 prod）+ 可选 `taskId`。
- 新增 facade 非流式评测出口；线上 SSE 对话行为不变（默认 prod）。

### D8. 跨服务：HTTP + Nacos 发现

- 调用协议仍为 HTTP JSON facade（`httpx`），非 gRPC。
- content / retrieval / admin 启动时注册到 Nacos（`NACOS_ENABLED=true`）；admin 按服务名选实例，失败回退静态 `*_BASE_URL`。
- 实现：`knowledge_common.nacos`（官方 `nacos-sdk-python` 的 `NacosNamingService`），默认关闭以免本地无 Nacos 时起不来。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Ragas vs Python 3.13 不兼容 | 先 POC 独立环境；固定裁判模型版本 |
| Agent 漏段/乱拉 | list 先行、段数/步数/token 预算、降级均匀抽样 |
| 出题+评测 LLM 成本高 | 配额写死、异步跑批、预算上限 |
| 跨服务 facade/MCP 从零 | 契约先定；MCP 与 RPC 共用分段实现 |
| 换集后旧 SUCCESS 可发 | 文档与 UI 提示；后续可收紧为当前测集 SUCCESS |
| 权限/data_scope | 评测与分段调用透传操作者或明确服务账号策略 |

## Migration Plan

1. 上线前：停用并删除 `embedding_auto_publish_job` / `auto_promote_completed_canary` 调用链；确认无残留定时。
2. 存量 canary：需经新建测评任务 → 至少一次 SUCCESS → 点发布，才能进 prod。
3. 回滚：若必须紧急上线，只能临时恢复 promote 调用路径（与本期哲学冲突，作事故预案而非产品能力）。

## Open Questions

- 生成 Agent / Ragas 裁判模型具体绑定哪套 `ai_model` / adapter（实现时对齐现有模型配置）。
- MCP 传输形态（stdio / SSE / 进程内 tool）以实现阶段选型为准，需求上只要 Agent 可调 list/get/search。
- `search_document_segments` 用 MySQL 关键词还是复用向量检索：优先能补洞即可，实现可选。
