## MODIFIED Requirements

### Requirement: 任务生命周期工具
系统 SHALL 为 Supervisor 提供任务工具：列表/查询、暂停、恢复、改范围预览与应用、删除、入库已爬内容、执行、重试；其中写操作 MUST 经 HITL。对用户与 Agent 可见文案 SHALL 使用「入库」语义，SHALL NOT 使用「合并已爬内容」等易与多页 Markdown 合并混淆的表述。

#### Scenario: 确认执行
- **WHEN** Supervisor 调用 `crawl_execute` 且用户 approve
- **THEN** 系统创建 `PENDING` 任务并投递爬取队列

#### Scenario: 确认入库已爬内容
- **WHEN** Supervisor 调用入库工具（如 `persist_crawl_results`）且用户 approve
- **THEN** 系统放弃失败 URL，将已成功页面投入文档落库队列（`crawl.document.pending`），任务进入可落库状态；HITL 确认文案表述为入库而非合并

### Requirement: 文档落库
系统 SHALL 在爬取 COMPLETED 后异步消费原文档 Topic，为该任务创建 1 条 `knowledge_document`（来源类型为网页爬取），并将每个成功且含 `doc_key` 的 URL 记录写入一条 `knowledge_document_file`（不合并多页 Markdown、不上传 merged 对象）；任务进入 CONVERTED（失败则为 CONVERT_FAILED 可重试）。多页合并实现代码若保留，MUST NOT 在默认落库路径调用。

#### Scenario: 多页爬取落库
- **WHEN** 任务 COMPLETED 且存在多个成功页面并进入落库消费者
- **THEN** 系统写入 1 条 `knowledge_document` 与 N 条 `knowledge_document_file`，MinIO 不新增合并结果对象，任务状态为 CONVERTED

#### Scenario: 落库失败可重试
- **WHEN** 落库过程异常
- **THEN** 任务进入 CONVERT_FAILED，可由定时任务重新投递同一 Topic 重试
