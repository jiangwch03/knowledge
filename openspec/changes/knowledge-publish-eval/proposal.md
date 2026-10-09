## Why

向量化完成后目前靠定时 auto-promote 直接 canary→prod，发布依据只有「写库成功」，缺少检索/生成质量的量化评估。需要在上线前用 Ragas 离线评测 + 人工决策，把发布入口收敛到 admin 测评任务。

## What Changes

- 在 **`knowledge-admin`** 落地测评集、生成 Agent、测评任务、评测 run/报告、点发布编排（主责；不新开服务）。
- **删除** embedding `auto-promote` 整条路径（调度与自动触发代码）；**不做** content 侧独立手动 promote；**唯一**发布入口为测评任务「发布」。
- 发布门槛：任务 `OPEN` 且历史上 **≥1 次** `run=SUCCESS`；换测评集不使旧 SUCCESS 失效。
- **生成 Agent + 分段 MCP** 一次出题（配额提示词写死：20～40 题，简单:中等:高难=1:2:1）；人工只改已有题；**不**手写录入、**不**增量补题。
- 评测表 `knowledge_eval_*` 与现有 `knowledge_*` **同库**，由 admin 维护。
- **改造问答 Agent**：透传 `releaseTag`/`taskId`（默认 prod；评测打 canary）；提供非流式评测出口 `{answer, contexts}`。
- content 暴露分段 list/get/search（MCP）与 embedding 任务查询、`promote` facade；admin 经 RPC 调用 content / retrieval。
- **不做**：A/B、Langfuse、指标自动门控发布、无测评旁路上 prod。

## Capabilities

### New Capabilities

- `knowledge-eval-dataset`: 按文档的独立测评集；生成 Agent + 分段 MCP 出题；人工改题约束与配额。
- `knowledge-eval-task`: 测评任务绑定测集与向量化任务；多跑 Ragas；报告；发布门槛与归档。
- `document-segment-mcp`: 文档分段 MCP（list/get/search），供出题 Agent 按需拉段。

### Modified Capabilities

- `document-embedding`: **BREAKING** 删除 auto-promote；promote 仅供 admin 测评编排调用；补充分段查询与任务查询 facade。
- `knowledge-qa-agent`: Agent 透传 `releaseTag`/`taskId`；新增非流式评测采数出口。

## Impact

- **服务**：`knowledge-admin`（评测产品面 + Ragas 跑批 + 生成 Agent）、`knowledge-content`（删 auto-promote、MCP/分段/promote facade）、`knowledge-retrieval`（Agent 参数与评测 facade）。
- **数据**：新增 `knowledge_eval_dataset` / `item` / `task` / `run` / `run_item`（同库）。
- **依赖**：Ragas（需验证 Python 版本兼容）；MCP 基建（仓库尚无）；跨服务 facade/RPC 首批落地。
- **参考**：`docs/rag/知识库发布评测方案.md`。
