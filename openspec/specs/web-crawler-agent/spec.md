## Purpose

网页爬取顾问型 Agent：会话式探站与策略生成、试爬门禁、HITL 确认后异步 crawl4ai 执行，并将 Markdown 落库为知识库文档。

## Requirements

### Requirement: Agent 会话管理
系统 SHALL 使用通用 Agent 会话表管理网页爬取会话（`knowledge_agent_session`，`agent_type=web_crawler`），支持创建、查询、重命名、关闭、删除。

#### Scenario: 创建新会话
- **WHEN** 用户创建会话
- **THEN** 系统写入 `knowledge_agent_session`，状态 `ACTIVE`，返回会话信息

#### Scenario: 查询会话列表
- **WHEN** 用户查询本人列表或数据权限列表
- **THEN** 系统分别通过 `/crawler/session/list` 与 `/list-all` 分页返回

#### Scenario: 删除会话
- **WHEN** 用户删除会话
- **THEN** 系统软删除会话及其 `knowledge_agent_message`

### Requirement: Agent 消息存储
系统 SHALL 在 `knowledge_agent_message` 中存储消息，角色与 LangChain 对齐：`human` / `ai` / `system` / `tool`。

#### Scenario: 获取历史消息
- **WHEN** 用户请求历史消息
- **THEN** 系统分页返回该会话消息

### Requirement: Agent 对话 SSE
系统 SHALL 提供 SSE：`POST /crawler/chat/{session_id}/message` 与 `POST /crawler/chat/{session_id}/resume`。

#### Scenario: 流式事件
- **WHEN** Agent 运行
- **THEN** 系统推送 `token`、工具相关事件、`message`、`user_choice`、`error`、`done`，并标注 `supervisor` / `subagent` 来源

#### Scenario: HITL 恢复
- **WHEN** 用户对写工具确认卡选择 approve 或 reject
- **THEN** 系统经 resume 接口继续或取消该工具执行

### Requirement: Supervisor + Planning 架构
系统 SHALL 以 deepagents Supervisor 为根图，并通过 `task` 委派 Planning 子 Agent；Supervisor SHALL NOT 直接调用探站工具。

#### Scenario: 新爬策略生成
- **WHEN** 用户提供目标 URL 与意图
- **THEN** Supervisor 委派 Planning 完成探站、生成 `crawl_config` 并执行试爬

### Requirement: Planning 工具链
系统 SHALL 为 Planning 提供探站与试爬工具：`fetch_robots_txt`、`fetch_sitemap`、`fetch_page`、`probe_rendered_page`、`anti_crawling_test`、`query_proxy_pool`、`trial_crawl`。

#### Scenario: 试爬
- **WHEN** Planning 调用 `trial_crawl`
- **THEN** 系统以受限页数/深度试爬并写入会话级 Redis 试爬指纹

### Requirement: 正式提交门禁
系统 SHALL 在 `crawl_execute` / `crawl_retry` / 改范围提交前校验试爬指纹与 seed/filter 一致性；未通过则拒绝提交。

#### Scenario: 无试爬指纹
- **WHEN** 用户确认爬取但无匹配指纹
- **THEN** 工具返回失败说明，不创建正式任务

### Requirement: 任务生命周期工具
系统 SHALL 为 Supervisor 提供任务工具：列表/查询、暂停、恢复、改范围预览与应用、删除、入库已爬内容、执行、重试；其中写操作 MUST 经 HITL。对用户与 Agent 可见文案 SHALL 使用「入库」语义，SHALL NOT 使用「合并已爬内容」等易与多页 Markdown 合并混淆的表述。

#### Scenario: 确认执行
- **WHEN** Supervisor 调用 `crawl_execute` 且用户 approve
- **THEN** 系统创建 `PENDING` 任务并投递爬取队列

#### Scenario: 确认入库已爬内容
- **WHEN** Supervisor 调用入库工具（如 `persist_crawl_results`）且用户 approve
- **THEN** 系统放弃失败 URL，将已成功页面投入文档落库队列（`crawl.document.pending`），任务进入可落库状态；HITL 确认文案表述为入库而非合并

### Requirement: 任务状态机
系统 SHALL 维护任务状态：PENDING、RUNNING、PAUSED、COMPLETED、CONVERTING、CONVERT_FAILED、CONVERTED、FAILED、USER_DECISION。

#### Scenario: 规则重试触顶
- **WHEN** 自动重试达到上限
- **THEN** 任务进入 `USER_DECISION`，可由会话内 Agent 修复后 `crawl_retry`

### Requirement: URL 记录
系统 SHALL 在 `knowledge_web_crawler_task_url_record` 记录每 URL 的 SUCCESS/FAILED 与 `doc_key`；失败明细通过该表查询，不依赖独立 failed_url 表。

### Requirement: 文档落库
系统 SHALL 在爬取 COMPLETED 后异步消费原文档 Topic，为该任务创建 1 条 `knowledge_document`（来源类型为网页爬取），并将每个成功且含 `doc_key` 的 URL 记录写入一条 `knowledge_document_file`（不合并多页 Markdown、不上传 merged 对象）；任务进入 CONVERTED（失败则为 CONVERT_FAILED 可重试）。多页合并实现代码若保留，MUST NOT 在默认落库路径调用。

#### Scenario: 多页爬取落库
- **WHEN** 任务 COMPLETED 且存在多个成功页面并进入落库消费者
- **THEN** 系统写入 1 条 `knowledge_document` 与 N 条 `knowledge_document_file`，MinIO 不新增合并结果对象，任务状态为 CONVERTED

#### Scenario: 落库失败可重试
- **WHEN** 落库过程异常
- **THEN** 任务进入 CONVERT_FAILED，可由定时任务重新投递同一 Topic 重试

### Requirement: 模型选择
系统 SHALL 通过适配点 `web_crawler_agent` 提供可选模型列表，并支持按请求 `model_id` 切换。

#### Scenario: 列出模型
- **WHEN** 前端请求 `/crawler/chat/models`
- **THEN** 系统返回该适配点下启用的模型配置
