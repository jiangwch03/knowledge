## Why

RAG 知识库需要持续补充高质量 Markdown。整站爬取配置门槛高，需要顾问型 Agent：用户给 URL 与业务意图，系统完成探站、策略、试爬校验，确认后异步爬取并落库。

## What Changes（As-Built）

- 前端「知识管理 → 网页爬虫」：会话 SSE、HITL 确认、任务/文档 Tab。
- 后端 `knowledge-content`：
  - **deepagents Supervisor + Planning 子 Agent**（非早期单主 Agent 方案）；
  - Planning 工具：robots / sitemap / page / probe / anti / proxy / trial；
  - Supervisor 工具：任务查询与写生命周期（execute/retry/pause/resume/rescope/merge/delete）；
  - 写工具 **HITL**（approve/reject）+ **试爬指纹门禁**；
  - crawl4ai（0.9.0）异步执行；结果 MinIO + `knowledge_document`。
- 会话落通用表 `knowledge_agent_session` / `knowledge_agent_message`（`agent_type=web_crawler`）。
- 任务表 `knowledge_web_crawler_task` + URL 记录表；无独立 failed_url / 会话-任务关联表。
- 模型：管理端适配点 `web_crawler_agent`，运行时可切换。
- 范围不含 embedding / 分块 / 向量库。

详细设计见 `docs/rag/网页爬取Agent/` 与本目录 `design.md`。

## Capabilities

### New Capabilities

- `web-crawler-agent`: 会话、Supervisor/Planning、试爬门禁、任务执行与状态、文档落库。

### Modified Capabilities

- `rag-document-upload`: 文档来源类型扩展「网页爬取」；复用 MinIO、版本、落库。

## Impact

- **knowledge-web**: 爬虫页与 content API。
- **knowledge-content**: Agent、executor、consumer、scheduler。
- **knowledge-common**: Agent 会话/消息、Checkpointer、SSE runtime、模型适配。
- **knowledge-admin**: 模型与 `web_crawler_agent` 适配点。
- **依赖**: crawl4ai、langchain、langgraph、deepagents。
