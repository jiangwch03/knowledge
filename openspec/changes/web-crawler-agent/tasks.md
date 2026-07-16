## 1. 数据库迁移

- [x] 1.1 创建 `web_crawler_session` 表
- [x] 1.2 创建 `web_crawler_message` 表
- [x] 1.3 创建 `crawl_task` 表
- [x] 1.4 创建 `crawl_task_failed_url` 表
- [x] 1.5 创建 `web_crawler_session_task` 关联表
- [x] 1.6 创建 `web_crawler_message_task` 关联表
- [x] 1.7 扩展 `knowledge_document` 表，添加 `task_id`、`source_url` 字段
- [x] 1.8 初始化 `DocumentSourceType` 枚举，添加「网页爬取」类型

## 2. 后端共享层 (`knowledge-common`)

- [x] 2.1 扩展 `DocumentSourceType` 枚举，添加 `WEB_CRAWLER` 类型

## 3. 后端业务层 (`knowledge-content`) - 数据模型

- [x] 3.1 创建 `web_crawler_session` DO/DAO/VO
- [x] 3.2 创建 `web_crawler_message` DO/DAO/VO
- [x] 3.3 创建 `crawl_task` DO/DAO/VO
- [x] 3.4 创建 `crawl_task_failed_url` DO/DAO/VO
- [x] 3.5 创建 `web_crawler_session_task` DO/DAO/VO
- [x] 3.6 创建 `web_crawler_message_task` DO/DAO/VO

## 4. 后端业务层 (`knowledge-content`) - Agent 模块

- [x] 4.1 创建 `agents/` 包结构（`__init__.py`、`crawler_agent.py`、`nodes/`、`states/`、`tools/`）
- [x] 4.2 实现 `CrawlerAgentState` TypedDict 定义
- [x] 4.3 实现 `fetch_robots_txt` 工具（薄适配层：定义 LangGraph 工具接口，复杂解析逻辑下沉到 `WebCrawlerAnalysisService`）
- [x] 4.4 实现 `fetch_sitemap` 工具（薄适配层：定义 LangGraph 工具接口，复杂解析逻辑下沉到 `WebCrawlerAnalysisService`）
- [x] 4.5 实现 `fetch_page` 工具（薄适配层：定义 LangGraph 工具接口，页面分析逻辑下沉到 `WebCrawlerAnalysisService`）
- [x] 4.6 实现 `test_anti_crawling` 工具（薄适配层：定义 LangGraph 工具接口，反爬检测逻辑下沉到 `WebCrawlerAnalysisService`）
- [x] 4.7 实现 `analyze_url_patterns` 工具（薄适配层：定义 LangGraph 工具接口，URL 模式分析逻辑下沉到 `WebCrawlerAnalysisService`）
- [x] 4.8 实现 `analyze` 节点（ReAct 循环体）
- [x] 4.9 实现 `reflect` 节点（Reflection 自审）
- [x] 4.10 实现 `ask_user` 节点（用户提问）
- [x] 4.11 实现 `generate` 节点（策略生成）
- [x] 4.12 实现 `confirm` 节点（策略确认，interrupt 点）
- [x] 4.13 实现 `output` 节点（输出最终 JSON）
- [x] 4.14 构建 LangGraph StateGraph，串联节点、条件边、中断点
- [x] 4.15 实现提示词配置（`crawler_agent_system`、`crawler_reflection`、`crawler_retry_analysis`、`crawler_summary`），覆盖参数四分类逻辑：固定默认参数（第一类，原样填入）、配置参数（第二类，用户回答直接映射）、LLM 自动推导（第三类，基于分析结果推理）、Hook 声明（第四类，输出结构化声明由代码层动态构建）

## 5. 后端业务层 (`knowledge-content`) - 服务层

- [x] 5.1 实现 `WebCrawlerSessionService`（会话 CRUD、状态管理）
- [x] 5.2 实现 `WebCrawlerMessageService`（消息 CRUD、历史查询）
- [x] 5.3 实现 `CrawlTaskService`（任务 CRUD、状态更新、进度查询）
- [x] 5.4 实现 `CrawlTaskFailedUrlService`（失败 URL 记录、查询）
- [x] 5.5 实现 `CrawlerAgentService`（Agent 对话编排、SSE 流式响应）
- [x] 5.6 实现 `CrawlTaskExecutorService`（crawl4ai 爬取执行、结果处理）
- [x] 5.7 实现 `CrawlTaskRetryService`（失败自动修复、静默 LLM 调用）
- [x] 5.8 实现 `CrawlerDocumentService`（文档落库、版本管理）

## 6. 后端业务层 (`knowledge-content`) - 控制器层

- [x] 6.1 实现 `WebCrawlerSessionController`（会话 CRUD 接口）
- [x] 6.2 实现 `WebCrawlerChatController`（Agent 对话 SSE 接口）
- [x] 6.3 实现 `CrawlTaskController`（任务提交、查询、失败 URL 查询接口）
- [x] 6.4 实现 `CrawlerDocumentController`（文档列表、预览、下载接口）
- [x] 6.5 实现数据权限控制（复用 RuoYi 框架的 `DataScopeDependency`，确保用户只能查看自己或本部门的会话和任务）

## 7. 后端业务层 (`knowledge-content`) - 消费者与定时任务

- [x] 7.1 实现 `CrawlTaskConsumer`（爬取任务执行消费者，消息队列负责削峰和任务排队）
- [x] 7.2 实现 `CrawlTaskTimeoutJob`（任务超时兜底定时任务）
- [x] 7.3 实现 `CrawlTaskRetryJob`（失败任务重试定时任务）
- [x] 7.4 实现站内通知（复用 RuoYi 框架的通知功能，任务失败时发送站内通知，通知内容包含跳转链接到聊天框页面）
- [x] 7.5 实现并发控制（`asyncio.Semaphore` 限制最大并发任务数为 3）
- [x] 7.6 实现浏览器实例全局复用（`AsyncWebCrawler` 单例，`user_agent` 固定为 `chrome` 模式，`cache_mode` 固定启用 `ENABLED`，相同 URL 不重复请求）

## 8. 后端业务层 (`knowledge-content`) - 数据压缩

- [x] 8.1 实现工具内部压缩（`fetch_robots_txt`、`fetch_sitemap`、`fetch_page`、`test_anti_crawling`、`analyze_url_patterns`）
- [x] 8.2 实现对话历史压缩（过滤 tool 消息、滑动窗口、历史摘要）
- [x] 8.3 实现 Token 预算管控（单轮总消耗 ≤ 10,000 tokens）

## 9. 后端管理后台 (`knowledge-admin`)

- [x] 9.1 注册网页爬取相关接口的权限编码
- [x] 9.2 配置菜单结构（知识管理 → 网页爬虫）
- [x] 9.3 改造模型功能适配，支持一个业务配置多个模型
- [x] 9.4 在模型功能适配中新增 `web_crawler_agent` 功能点
- [x] 9.5 初始化 `web_crawler_agent` 功能点的模型配置数据（关联 Qwen-Plus 模型）

## 10. 前端 (`knowledge-web`) - 页面结构

- [x] 10.1 新增「知识管理 → 网页爬虫」路由配置
- [x] 10.2 实现页面整体布局（左侧会话列表 + 右侧聊天区）
- [x] 10.3 实现会话列表区组件
- [x] 10.4 实现聊天消息区组件

## 11. 前端 (`knowledge-web`) - 会话管理

- [x] 11.1 实现新建会话功能
- [x] 11.2 实现会话列表展示与搜索
- [x] 11.3 实现会话重命名功能
- [x] 11.4 实现会话删除功能（二次确认）
- [x] 11.5 实现会话状态展示（`ACTIVE` / `CLOSED`）

## 12. 前端 (`knowledge-web`) - 聊天交互

- [x] 12.1 实现消息输入框（多行文本、Shift+Enter 换行、Enter 发送）
- [x] 12.2 实现消息发送功能（调用 SSE 接口）
- [x] 12.3 实现 SSE 流式响应处理（token 输出、工具调用、完成事件）
- [x] 12.4 实现消息气泡渲染（user 右对齐、assistant 左对齐、system 居中、tool 折叠卡片）
- [x] 12.5 实现工具调用卡片（折叠态展示工具名称、展开态展示输入输出 JSON）
- [x] 12.6 实现 Markdown 渲染（代码高亮、表格渲染）
- [x] 12.7 实现消息操作（复制、重新生成最后一条回复）
- [x] 12.8 实现停止生成功能（中断 SSE 连接）
- [x] 12.9 实现模型选择下拉（从 `knowledge-admin` 已配置模型中选择）

## 13. 前端 (`knowledge-web`) - 策略确认

- [x] 13.1 实现策略确认卡片组件
- [x] 13.2 实现配置摘要展示（按七大配置主题分组、参数来源标注）
- [x] 13.3 实现「确认配置」按钮（提交后台爬取任务）
- [x] 13.4 实现「重新生成」按钮（触发 Agent 重新推理）
- [x] 13.5 实现「修改参数」按钮（配置摘要变为可编辑表单）
- [x] 13.6 实现重复爬取限制提示

## 14. 前端 (`knowledge-web`) - 任务进度

- [x] 14.1 实现任务进度卡片组件
- [x] 14.2 实现状态标签展示（`PENDING` / `RUNNING` / `COMPLETED` / `FAILED` / `USER_DECISION`）
- [x] 14.3 实现进度条展示（百分比 + 条形进度条）
- [x] 14.4 实现当前步骤文字提示
- [x] 14.5 实现统计数据展示（成功页面数 / 失败页面数）
- [x] 14.6 实现轮询更新（调用 `GET /api/rag/crawler/task/{task_id}`）

## 15. 前端 (`knowledge-web`) - 任务列表

- [x] 15.1 实现任务 Tab 切换（聊天 / 任务）
- [x] 15.2 实现历史爬取任务列表
- [x] 15.3 实现失败任务详情展示（失败原因、已尝试修复、建议方案）
- [x] 15.4 实现失败任务跳转定位（跳转至聊天 Tab 消息流底部）
- [x] 15.5 实现用户决策操作（调整参数重试 / 放弃删除）

## 16. 前端 (`knowledge-web`) - 文档管理

- [x] 16.1 实现爬取结果文档列表组件
- [x] 16.2 实现文档预览功能（Markdown 渲染弹窗）
- [x] 16.3 实现文档下载功能

## 17. 前端 (`knowledge-web`) - 代理配置

- [x] 17.1 在 `vite.config.js` 中新增 `knowledge-content` 代理配置
- [x] 17.2 在 nginx 配置中新增 `knowledge-content` 代理配置

## 18. 测试

- [x] 18.1 编写 Agent 工具单元测试（`fetch_robots_txt`、`fetch_sitemap`、`fetch_page`、`test_anti_crawling`、`analyze_url_patterns`）
- [x] 18.2 编写 Agent 节点单元测试（`analyze`、`reflect`、`ask_user`、`generate`、`confirm`、`output`）
- [x] 18.3 编写服务层单元测试（`WebCrawlerSessionService`、`WebCrawlerMessageService`、`CrawlTaskService`）
- [x] 18.4 编写控制器层集成测试（会话 CRUD、Agent 对话、任务提交查询）
- [x] 18.5 编写前端组件单元测试（会话列表、聊天消息、策略确认卡片、任务进度卡片）

## 19. 部署与配置

- [x] 19.1 安装 Python 依赖（`crawl4ai`、`langchain`、`langchain-openai`、`langgraph`）
- [x] 19.2 安装 Playwright + Chromium 浏览器依赖
- [x] 19.3 配置 Docker 镜像（浏览器运行依赖）
- [x] 19.4 配置 prompts.yaml（`crawler_agent_system`、`crawler_reflection`、`crawler_retry_analysis`、`crawler_summary`）
- [x] 19.5 执行数据库迁移脚本
- [x] 19.6 验证端到端流程（创建会话 → 发送 URL → Agent 分析 → 策略确认 → 任务执行 → 文档落库）