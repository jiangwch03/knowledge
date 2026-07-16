## Why

随着 RAG 知识库建设深入，系统需要持续补充高质量的 Markdown 数据源。当前数据主要依赖人工整理与单文件上传，来源单一、入库效率低，难以支撑对公开网站、技术文档站、产品博客等整站内容的自动化采集。

网页爬取技术存在较高门槛：crawl4ai 涉及深度爬取策略、URL 过滤链、反爬对抗、代理轮换、HTML 解析、缓存配置、Hook 注入等七大配置主题，普通用户难以理解这些技术参数的含义和抉择。

为扩展知识来源、降低人工录入成本，需要建设一套**爬取顾问型 Agent**：用户仅提供目标网址，Agent 自动执行站点预分析，基于分析结果主动向用户发起业务导向的提问，自动生成完整的 crawl4ai 爬取策略配置，经用户确认后提交后台异步任务执行，最终将爬取结果 Markdown 落库。

## What Changes

- 前端新增「知识管理 → 网页爬虫」独立页面，支持会话式 Agent 交互、策略确认、任务进度感知与结果管理。
- 后端在 `knowledge-content` 中实现基于 LangGraph + crawl4ai 的整站爬取 Agent：
  - Agent 作为「爬取顾问」，通过站点预分析 + 主动提问引导用户完成 crawl4ai 七大配置主题的策略生成；
  - 5 个分析工具（`fetch_robots_txt`、`fetch_sitemap`、`fetch_page`、`test_anti_crawling`、`analyze_url_patterns`）作为 LangGraph Tool 注册；
  - 大模型选用 Qwen-Plus，通过 LangChain `ChatTongyi` 接入；
  - crawl4ai 负责实际整站爬取与结构化 Markdown 输出；
  - 爬取结果写入 MinIO，并生成 `knowledge_document` 记录。
- 对话阶段（策略生成）与执行阶段（爬取任务）解耦：对话通过 SSE 流式响应，爬取通过后台异步任务执行。
- `knowledge-common` 提供 `ai_models` 等共享模型配置能力，`knowledge-admin` 保留模型管理入口。
- 本次范围不涉及 embedding 与文档分块的具体实现，但表结构需预留扩展字段。

## Capabilities

### New Capabilities

- `web-crawler-agent`: 网页爬取 Agent 核心能力，包括会话管理、站点分析工具链、策略生成、任务执行与状态管理、文档落库全生命周期。

### Modified Capabilities

- `rag-document-upload`: 需要扩展文档来源类型枚举，支持「网页爬取」作为新的文档来源；复用文档版本管理、MinIO 服务、文档落库逻辑。

## Impact

- **前端 (`knowledge-web`)**: 新增「网页爬虫」页面组件、会话管理、聊天交互、策略确认卡片、任务进度展示、文档预览下载等功能。
- **后端 (`knowledge-content`)**: 新增 LangGraph Agent 模块、crawl4ai 爬取执行器、任务状态管理、会话消息存储、文档落库逻辑。
- **共享层 (`knowledge-common`)**: 扩展文档来源类型枚举，复用 MinIO 服务、文档版本管理、消息流基础设施。
- **管理后台 (`knowledge-admin`)**: 保留 AI 模型管理页面，模型配置共享给 `knowledge-content`。
- **数据库**: 新增 `web_crawler_session`、`web_crawler_message`、`crawl_task`、`crawl_task_failed_url` 等表；`knowledge_document` 表扩展来源类型。
- **依赖**: 新增 crawl4ai、LangChain、LangGraph 等 Python 依赖。