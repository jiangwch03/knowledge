# Web Crawler Agent — Design (As-Built)

> 实现以代码与 `docs/rag/网页爬取Agent/` 为准。本 change 的早期「单主 Agent + 5 Tool、不用 Multi Agent」方案**已废弃**。

## Context

RAG 知识库需要整站 Markdown 采集能力。用户难以直接配置 crawl4ai，因此提供顾问型 Agent：探站 → 策略 → 试爬 → HITL 确认 → MQ 异步执行 → 文档落库。

### Goals

1. 会话式 SSE 交互（通用 `knowledge_agent_*`，`agent_type=web_crawler`）
2. **Supervisor + Planning** 多 Agent（deepagents）
3. 试爬指纹门禁后再正式提交
4. 任务生命周期（暂停/恢复/改范围/重试/合并）
5. crawl4ai 执行 + MinIO + `knowledge_document`
6. 前端：会话 / 任务 / 文档三 Tab

### Non-Goals

- Embedding / 向量库 / 检索
- 独立 `POST /crawler/task` 建任务（任务由 Agent 工具创建）
- 父图 `interrupt_gate` 策略确认节点（改为工具 `interrupt_on`）

## Decisions

### D1: deepagents Supervisor + Planning SubAgent

- Supervisor：场景编排 + 任务写工具；通过框架 `task` 委派 Planning
- Planning：7 个探站/试爬工具；`ModelCallLimitMiddleware`（默认 50）
- 根图 = Supervisor，无额外父包装

### D2: 对话与执行解耦

- SSE：`/crawler/chat/{id}/message|resume`
- 执行：MQ `crawl.task.pending` → executor；文档 `crawl.document.pending`

### D3: HITL 在写工具上

- `interrupt_on`：`crawl_execute` / `crawl_retry` / pause / resume / delete / merge / `apply_scope_change`
- 前端 `user_choice` → resume `approve|reject`

### D4: 试爬硬门禁

- Redis 指纹绑定 session + url + sanitized config；正式 execute/retry/rescope 前校验

### D5: 通用会话表 + URL 记录表

- `knowledge_agent_session` / `knowledge_agent_message`
- `knowledge_web_crawler_task` + `knowledge_web_crawler_task_url_record`
- 不再使用独立 failed_url / session-task 关联表

### D6: 可配置模型

- 适配点 `web_crawler_agent`；运行时 `model_id` + middleware 换模

## Architecture (summary)

详见 `docs/rag/网页爬取Agent/03-架构设计.md`。

```
FE → Controllers → CrawlerAgentService → Supervisor
                         └─ task → Planning (probe + trial)
                         └─ crawl_execute HITL → MQ → crawl4ai → document
```

## Risks / Mitigations

| Risk | Mitigation |
|------|------------|
| 坏配置冲全站 | trial 门禁 + max_pages / filter |
| deepagents state 丢失 | state_schema 映射补丁 |
| 长会话 token | Planning 工具压缩返回；建议新会话 |
| FAILED 被当成终态 | Prompt/产品说明：仅 USER_DECISION 人工修 |

## Doc index

| 文档 | 内容 |
|------|------|
| `docs/rag/网页爬取Agent/01-需求设计.md` | 产品与页面 |
| `02-技术选型.md` | 栈与模式 |
| `03-架构设计.md` | Agent/工具/SSE |
| `04-交互流程设计.md` | 状态机与 MQ |
| `05-用户操作交互时序图.md` | 时序 |
| `06-数据库设计.md` | 表结构 |
| `07-后端接口设计.md` | API |
| `08-数据量评估.md` | 容量 |
| `09-Agent图结构调试手册.md` | 调试 |
