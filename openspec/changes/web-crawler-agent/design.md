## Context

当前 RAG 知识库数据主要依赖人工整理与单文件上传，来源单一、入库效率低。网页爬取技术存在较高门槛，涉及深度爬取策略、URL 过滤链、反爬对抗、代理轮换、HTML 解析、缓存配置、Hook 注入等七大配置主题，普通用户难以理解。

需要建设一套**爬取顾问型 Agent**，用户仅提供目标网址，Agent 自动执行站点预分析，基于分析结果主动向用户发起业务导向的提问，自动生成完整的 crawl4ai 爬取策略配置，经用户确认后提交后台异步任务执行，最终将爬取结果 Markdown 落库。

### 现有系统状态

- **前端 (`knowledge-web`)**: Vue3 + Element Plus，已有「资料上传」页面，支持文件上传、MinerU 解析、文档预览下载。
- **后端 (`knowledge-content`)**: FastAPI，已有文档上传、MinerU 解析任务调度、状态流转、Markdown 合并入库的完整流程。
- **共享层 (`knowledge-common`)**: 提供 MinIO 服务、文档版本管理、消息流基础设施、Redis 分布式锁等通用能力。
- **管理后台 (`knowledge-admin`)**: 保留 AI 模型管理页面，模型配置共享给 `knowledge-content`。
- **数据库**: 已有 `knowledge_document`、`knowledge_upload_document_record`、`knowledge_mineru_parse_task` 等表。

### 约束条件

- 复用现有 `knowledge_document` 文档主表，扩展来源类型枚举。
- 复用现有 MinIO 服务、文档版本管理、消息流基础设施。
- 大模型选用 Qwen-Plus，通过 LangChain `ChatTongyi` 接入。
- 爬取引擎使用 crawl4ai 0.8.9。
- Agent 框架使用 LangGraph + LangChain。

## Goals / Non-Goals

**Goals:**

1. **会话式 Agent 交互**: 用户通过自然语言与 Agent 对话，Agent 主动提问引导用户完成爬取策略配置。
2. **站点预分析**: Agent 调用 5 个分析工具（`fetch_robots_txt`、`fetch_sitemap`、`fetch_page`、`test_anti_crawling`、`analyze_url_patterns`）自动分析目标站点。
3. **策略生成**: Agent 基于分析结果与用户回答，自动生成完整的 crawl4ai 爬取策略配置。
4. **任务执行**: 用户确认策略后，后台异步执行 crawl4ai 爬取任务，实时更新进度。
5. **文档落库**: 爬取结果 Markdown 写入 MinIO，并生成 `knowledge_document` 记录。
6. **状态管理**: 任务状态管理，支持失败重试、用户决策、自动修复等场景。
7. **前端页面**: 新增「知识管理 → 网页爬虫」独立页面，支持会话管理、聊天交互、策略确认、任务进度展示、文档预览下载。

**Non-Goals:**

1. **Embedding 计算**: 本次不涉及文档分块与向量化。
2. **向量库写入**: 本次不涉及向量数据库操作。
3. **检索排序逻辑**: 本次不涉及 RAG 检索与排序。
4. **多 Agent 协作**: 采用「主 Agent + 纯 Tool」架构，不涉及多 Agent 协调。
5. **实时流式爬取**: 采用后台异步任务，不支持实时流式爬取结果。

## Decisions

### Decision 1: Agent 架构模式 — ReAct + Reflection + Human-in-the-Loop 组合

**选择**: 对话阶段采用 ReAct + Reflection + Human-in-the-Loop 组合架构。

**理由**:
- **ReAct（最多 3 轮）**: 5 个工具有依赖关系（`fetch_sitemap` 结果决定是否 `analyze_url_patterns`，`fetch_page` 结果决定是否 `test_anti_crawling`），无法一次性规划，需要动态决策。
- **Reflection（单次）**: ReAct 结束后追加一次自审，判断分析结果是否充分，不足则追问用户。
- **Human-in-the-Loop**: 策略确认点等待用户审批，支持修改参数、重新生成、确认三种操作。

### Decision 2: 对话阶段与执行阶段解耦

**选择**: 对话阶段（策略生成）与执行阶段（爬取任务）完全解耦。

**理由**:
- **对话阶段（秒级，同步 SSE）**: 用户发送消息 → Agent 调用分析工具 → 主动提问 → 生成策略配置，通过 SSE 流式响应。
- **执行阶段（分钟级，异步后台任务）**: 用户确认策略配置后，接口立即返回 `task_id`，后台 Worker 异步执行 crawl4ai 爬取。
- **用户决策中断**: 任务进入 `USER_DECISION` 状态时暂停执行，通过消息流通知前端。

**优势**:
- 用户关闭页面不影响任务执行，下次进入会话可看到任务状态。
- 系统重启后，兜底定时任务可扫描未完成任务并重新拉起。

### Decision 3: 数据压缩与成本控制

**选择**: 三层压缩方案：工具内部压缩 + 对话历史压缩 + Token 预算管控。

**理由**:
- **工具内部压缩（最关键）**: 每个 Tool 在返回给 Agent 前，自行完成「原始数据 → 结构化结论」的精炼，单轮工具总计 ≤ 1,900 tokens。
- **对话历史压缩**: 工具调用的原始结果不保留在 LLM 对话历史中，只保留 Agent 基于工具结果生成的总结性回复；滑动窗口 + 历史摘要，对话历史总计 ≤ 4,000 tokens。
- **Token 预算管控**: 单轮总消耗 ≤ 10,000 tokens，含所有输入输出。

**成本估算**: 单个任务全生命周期 ≈ ¥0.06（按 Qwen-Plus 定价）。

### Decision 4: 参数四分类与权责模型

**选择**: 将 crawl4ai 参数分为四类，严格按分类处理。

**理由**:
- **第一类：固定默认（不分析、不提问）**: 使用固定默认值，每次输出 JSON 时按固定值原样填入。
- **第二类：配置参数（问用户后直接映射 JSON 字段）**: 用户回答直接填入对应的 JSON 配置字段。
- **第三类：LLM 自动推导（分析后自行决策，不提问）**: Agent 调用分析工具后，基于结构化返回结果自行推理决策。
- **第四类：Hook 声明（问用户后输出为可执行声明，代码层动态构建）**: 检测到相应场景时向用户提问，收集意图后输出结构化 Hook 声明。

**核心原则**: 用户管「爬什么」（范围、维度、媒体），Agent 管「怎么爬」（策略、反爬、解析），代码层管「如何执行」（按 Hook 声明构建运行时逻辑）。

### Decision 5: 代码包结构 — Agent 模块自包含

**选择**: Agent 相关代码统一收归 `agents/` 包，内部自包含，与 `service/`、`mapper/` 等业务包平级。

**理由**:
- **职责清晰**: `agents/` 包负责 Agent 逻辑，`service/` 包负责业务逻辑，`mapper/` 包负责数据访问。
- **tools 与 service 层职责边界**: `agents/tools/` 作为薄适配层，仅负责定义 LangGraph 工具接口，复杂业务逻辑下沉到 `service/` 层复用。

### Decision 6: 数据库设计 — 新增表与扩展现有表

**选择**: 新增 `web_crawler_session`、`web_crawler_message`、`crawl_task`、`crawl_task_failed_url` 等表；`knowledge_document` 表扩展来源类型。

**理由**:
- **会话管理**: `web_crawler_session` 存储 Agent 会话基本信息与状态，`web_crawler_message` 存储会话中的 user/assistant/system/tool 消息。
- **任务管理**: `crawl_task` 存储爬取任务状态、进度、配置、结果统计，`crawl_task_failed_url` 存储爬取失败的 URL 明细。
- **关联关系**: `web_crawler_session_task` 和 `web_crawler_message_task` 建立会话、消息与任务的多对多关联。
- **文档落库**: 复用现有 `knowledge_document` 表，扩展 `source_type` 枚举支持「网页爬取」。

**枚举设计**:
- **复用现有枚举**:
  - `DeleteFlag` - 删除标志（`knowledge-common`）
  - `DocumentSourceType` - 文档来源类型（`knowledge-common`，已包含 `CRAWL` 类型）
  - `DocumentStatus` - 文档状态（`knowledge-common`）
- **新建枚举**:
  - `CrawlTaskStatus` - 爬取任务状态（PENDING/RUNNING/COMPLETED/CONVERTED/CONVERT_FAILED/FAILED/USER_DECISION/PAUSED）
  - `SessionStatus` - 会话状态（ACTIVE/CLOSED）
  - `MessageRole` - 消息角色（user/assistant/system/tool）
  - `RelationType` - 关系类型（creator/reference）

## Risks / Trade-offs

### Risk 1: LLM 调用成本不可控

**风险**: Agent 对话阶段可能消耗大量 tokens，导致成本超预期。

**缓解措施**:
- 工具内部压缩：每个 Tool 返回结构化结论，单轮工具总计 ≤ 1,900 tokens。
- 对话历史压缩：滑动窗口 + 历史摘要，对话历史总计 ≤ 4,000 tokens。
- Token 预算管控：单轮总消耗 ≤ 10,000 tokens。
- 成本估算：单个任务全生命周期 ≈ ¥0.06。

### Risk 2: 工具调用失败或返回异常

**风险**: 分析工具可能因网络问题、目标站点异常等原因调用失败。

**缓解措施**:
- 工具调用重试机制：网络超时等可重试错误自动重试。
- 降级策略：工具调用失败时，Agent 基于已有信息继续推理，或向用户说明情况。
- 错误处理：工具返回异常时，记录详细错误信息，便于排查。

### Risk 3: 用户意图理解偏差

**风险**: Agent 可能误解用户意图，生成不符合预期的爬取策略。

**缓解措施**:
- 策略确认环节：用户确认前展示完整策略摘要，支持修改参数、重新生成。
- 多轮迭代：支持无限轮「重新生成」和「修改参数」迭代，直到用户满意。
- 透明化：参数标注来源标签（「用户选择」「自动适配」「固定默认」），便于用户理解。

### Risk 4: 爬取任务执行失败

**风险**: crawl4ai 爬取可能因反爬、网络、配置错误等原因失败。

**缓解措施**:
- 规则自动重试：最多 3 次规则重试。
- 静默修复：规则重试用尽后，静默调 LLM 分析失败原因，返回参数调整建议。
- 用户决策：自动修复用尽且为用户参数问题时，升级为 `USER_DECISION`，由用户选择重试或放弃。

### Risk 5: 系统资源消耗

**风险**: 大规模爬取可能消耗大量网络带宽、存储空间、CPU 资源。

**缓解措施**:
- 并发控制：`semaphore_count` 限制并发请求数。
- 页面限制：`max_pages` 限制最大爬取页面数。
- 深度限制：`max_depth` 限制爬取深度。
- 缓存机制：`cache_mode=ENABLED` 启用缓存，相同 URL 不重复请求。
- 架构扩展性：本次采用 SDK 方式集成 crawl4ai，做好封装处理；后续可独立部署 crawl4ai 服务，为切换爬取引擎预留扩展性。

## Migration Plan

### 阶段 1: 数据库迁移

1. 执行建表语句，创建 `web_crawler_session`、`web_crawler_message`、`crawl_task`、`crawl_task_failed_url`、`web_crawler_session_task`、`web_crawler_message_task` 表。
2. 扩展 `knowledge_document` 表，添加 `task_id`、`source_url` 字段。
3. 初始化 `DocumentSourceType` 枚举，添加「网页爬取」类型。

### 阶段 2: 后端迁移

1. 在 `knowledge-common` 中扩展 `DocumentSourceType` 枚举。
2. 在 `knowledge-content` 中实现 LangGraph Agent 模块、crawl4ai 爬取执行器、任务状态管理、会话消息存储、文档落库逻辑。
3. 在 `knowledge-content` 中实现 SSE 流式响应接口、任务查询接口、文档预览下载接口。
4. 在 `knowledge-admin` 中注册新接口的权限编码。

### 阶段 3: 前端迁移

1. 在 `knowledge-web` 中新增「知识管理 → 网页爬虫」页面组件。
2. 实现会话管理、聊天交互、策略确认卡片、任务进度展示、文档预览下载等功能。
3. 在 `vite.config.js` 和 nginx 配置中新增 `knowledge-content` 代理。

### 回滚策略

1. **数据库回滚**: 删除新增表，恢复 `knowledge_document` 表结构。
2. **后端回滚**: 回滚 `knowledge-content` 和 `knowledge-common` 代码变更。
3. **前端回滚**: 回滚 `knowledge-web` 代码变更。

## Resolved Questions

1. **模型配置管理**: 复用现有模型功能适配机制，在 `knowledge_ai_model_function_adapter` 表中新增 `web_crawler_agent` 功能点，支持配置多个模型。用户在创建会话时从该功能点配置的模型列表中选择。需改造现有模型功能适配，支持一个业务配置多个模型。
2. **权限粒度**: 不需要细粒度接口权限控制（如创建会话、提交任务、查看任务、删除会话等），但需要数据权限控制，确保用户不能查看别人的会话、任务或其他部门的数据。复用 RuoYi 框架的数据权限控制机制（`DataScopeDependency`）。
3. **监控告警**: 采用站内通知方式（复用 RuoYi 框架的通知功能），通知内容包含跳转链接，点击可跳转到对应的聊天框页面。
4. **日志审计**: 不需要额外的审计功能。对话日志已存储在 `web_crawler_message` 表，任务日志已存储在 `crawl_task` 表，RuoYi 框架的操作日志已覆盖接口级别的审计。
5. **性能优化**: 采用单机优化方案，不需要分布式爬取。具体策略：
   - **任务级并发控制**: 使用 `asyncio.Semaphore` 限制同时执行的爬取任务数（建议 `MAX_CONCURRENT_TASKS=3`）
   - **单任务内并发**: 通过 `semaphore_count` 参数控制（由 LLM 根据站点特征自动推导）
   - **浏览器实例复用**: 全局复用单个 `AsyncWebCrawler` 实例，`user_agent` 设为固定默认参数（`chrome` 模式），避免 `random` 模式导致实例无法复用
   - **缓存机制**: 固定启用 `cache_mode=ENABLED`，相同 URL 不重复请求

## Open Questions

（无）