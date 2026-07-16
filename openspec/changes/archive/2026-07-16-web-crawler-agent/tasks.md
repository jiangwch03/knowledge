# Tasks（历史清单，已过时）

> 下列勾选任务对应早期「单主 Agent + 专用 session 表」方案，**表名/架构均已演进**。  
> 现状请以 `design.md`、`proposal.md`、`specs/` 及 `docs/rag/网页爬取Agent/` 为准。  
> 本 change 功能已落地；归档时勿再按本清单核对实现。

## As-Built 完成摘要

- [x] 通用会话/消息：`knowledge_agent_session` / `knowledge_agent_message`
- [x] 任务 + URL 记录：`knowledge_web_crawler_task` / `knowledge_web_crawler_task_url_record`
- [x] deepagents Supervisor + Planning + HITL + 试爬门禁
- [x] SSE chat/resume、任务 REST、文档 list
- [x] MQ 执行与文档合并、调度兜底
- [x] 前端爬虫三 Tab
- [x] 设计文档已按实现回写（2026-07）
