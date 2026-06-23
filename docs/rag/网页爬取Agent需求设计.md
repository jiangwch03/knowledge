# 网页爬取 Agent 需求设计

## 一、需求背景与目标

### 1.1 背景

随着 RAG（检索增强生成）知识库建设的深入，系统需要持续补充高质量的 Markdown 格式数据源。当前知识库数据主要依赖人工整理与单文件上传，来源单一、入库效率低，难以支撑对公开网站、技术文档站、产品博客等整站内容的自动化采集。

为扩展知识来源、降低人工录入成本，需要建设一套基于自然语言交互的网页整站爬取 Agent：用户通过会话式对话描述爬取目标，Agent 自动分析意图、生成 crawl4ai 爬取策略，经用户确认后提交后台任务执行，最终将爬取结果 Markdown 落库，纳入统一的 `knowledge_document` 文档主表管理。

### 1.2 目标

- 前端新增「知识管理 → 网页爬虫」独立页面，支持会话式 Agent 交互、策略确认、任务进度感知与结果管理。
- 后端在 `knowledge-rag` 中实现基于 LangGraph + crawl4ai 的整站爬取 Agent：
  - LangGraph 编排分析、策略生成、确认、提交任务等节点；
  - crawl4ai 负责实际整站爬取与结构化 Markdown 输出；
  - 爬取结果写入 MinIO，并生成 `knowledge_document` 记录。
- `knowledge-common` 提供 `ai_models` 等共享模型配置能力，`knowledge-admin` 保留模型管理入口。
- 本次范围不涉及 embedding 与文档分块的具体实现，但表结构需预留扩展字段。

### 1.3 范围边界

| 范围 | 说明 |
|------|------|
| 包含 | 网页爬虫页面、LangGraph Agent、crawl4ai 爬取执行、任务状态管理、爬取结果落库、文档版本管理 |
| 不包含 | embedding 计算、文档分块、向量库写入、检索排序逻辑 |
| 依赖 | `knowledge-admin` 的 AI 模型配置、`knowledge-common` 的共享 DO/DAO/VO/消息流 |

---

## 二、总体流程

### 2.1 流程全景

```mermaid
graph TB
    A[新建/选择会话] --> B[用户发送爬取意图]
    B --> C[LangGraph Agent 分析生成策略]
    C --> D[展示目标URL与crawl4ai配置摘要]
    D --> E{用户确认?}
    E -->|重新生成| C
    E -->|修改参数| D
    E -->|确认| F[创建 crawl_task status=PENDING]
    F --> G[后台执行爬取]
    G --> H[更新 crawl_task 进度与状态]
    H --> I[成功: Markdown 落库 knowledge_document]
    H --> J[失败: 记录 crawl_task_failed_url]
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| `knowledge-web` | 新增「知识管理 → 网页爬虫」独立页面；通过代理访问 `knowledge-rag` 接口 |
| `knowledge-rag` | LangGraph Agent、crawl4ai 爬取执行、任务状态更新、文档落库 |
| `knowledge-admin` | 保留 AI 模型管理页面，模型配置共享给 `knowledge-rag` |
| `knowledge-common` | 兼容层：共享 `ai_models` DO/DAO/VO、消息流基础设施、MinIO/Redis 通用能力 |

### 2.3 数据流转总览

| 核心表 | 作用 |
|--------|------|
| `web_crawler_session` | 存储 Agent 会话基本信息与状态 |
| `web_crawler_message` | 存储会话中的 user/assistant/system/tool 消息 |
| `web_crawler_session_task` | 会话与爬取任务的关联 |
| `web_crawler_message_task` | 消息与爬取任务的关联 |
| `crawl_task` | 存储爬取任务状态、进度、配置、结果统计 |
| `crawl_task_failed_url` | 存储爬取失败的 URL 明细 |
| `knowledge_document` | 爬取成功后生成的文档主表记录 |

---

## 三、状态机与数据库标记

### 3.1 会话状态 `web_crawler_session.status`

| 状态值 | 含义 | 触发场景 |
|--------|------|----------|
| `ACTIVE` | 会话进行中 | 默认状态 |
| `CLOSED` | 会话已关闭 | 用户主动关闭或长时间未操作 |

### 3.2 消息角色 `web_crawler_message.role`

| 角色值 | 含义 | 入库时机 |
|--------|------|----------|
| `user` | 用户消息 | 用户发送消息后立即写入 |
| `assistant` | AI 回复 | Agent 完整回复结束后写入 |
| `system` | 系统提示 | 会话初始化或系统通知时写入 |
| `tool` | 工具调用结果 | Agent 调用工具后写入 |

### 3.3 爬取任务状态 `crawl_task.status`

| 状态值 | 含义 | 数据库标记变化 |
|--------|------|----------------|
| `PENDING` | 待执行 | `crawl_task.status='PENDING'`，`progress=0` |
| `RUNNING` | 执行中 | `crawl_task.status='RUNNING'`，`started_time=NOW()`，定时刷新 `progress`/`current_step` |
| `COMPLETED` | 完成 | `crawl_task.status='COMPLETED'`，`progress=100`，`completed_time=NOW()`，写入 `knowledge_document` |
| `FAILED` | 失败 | `crawl_task.status='FAILED'`，写入 `error_code`/`error_message`，记录 `crawl_task_failed_url` |
| `PAUSED` | 暂停 | 用户手动暂停（可选） |

### 3.4 失败记录 `crawl_task_failed_url`

- 单页爬取失败不中断整站任务，持续记录到 `crawl_task_failed_url`。
- 对超时、`503` 等 transient 错误按 `retry_count` 做有限重试。
- 浏览器进程崩溃、OOM、策略性失败需重新拉取任务，配合 `CacheMode.ENABLED` 减少重复请求。

---

## 四、前端页面与功能点

### 4.1 菜单结构

```
知识管理
├── 网页爬虫
├── 资料上传
└── embedding（占位）
```

### 4.2 网页爬虫页面

页面采用「左侧会话列表 + 右侧聊天区」布局。

#### 4.2.1 会话管理模块

- 新建爬取会话（调用 `POST /api/rag/crawler/session`）。
- 历史会话列表分页展示，支持按标题搜索（调用 `GET /api/rag/crawler/session/list`）。
- 点击会话加载历史消息并继续对话（调用 `GET /api/rag/crawler/session/{session_id}/messages`）。
- 会话重命名（调用 `PUT /api/rag/crawler/session/{session_id}`）。
- 删除会话（调用 `DELETE /api/rag/crawler/session/{session_id}`，级联软删除消息）。
- 会话状态展示：`ACTIVE` / `CLOSED`。

#### 4.2.2 Agent 聊天区模块

- 消息输入框：支持多行文本与换行。
- 发送消息：将 `user` 消息入库，并触发 SSE 流。
- SSE 流式返回 AI 回复（调用 `POST /api/rag/crawler/chat`）。
- 停止生成：前端中断 SSE 连接，已接收内容可选择性保存为不完整 `assistant` 消息。
- 重新生成最后一条回复：重新调用 SSE 接口。
- 模型选择下拉：从 `knowledge-admin` 已配置模型中选择，写入 `web_crawler_session.model_id`。
- 消息角色区分渲染：`user` / `assistant` / `system` / `tool`。
- Markdown / 代码块渲染。
- 复制单条消息。
- 清空当前会话消息（仅前端清空，可保留后端记录）。

#### 4.2.3 爬取策略确认模块

- Agent 分析用户意图后展示目标 URL。
- 展示生成的 crawl4ai 配置摘要（爬取深度、FilterChain、反爬参数等）。
- 用户可选择「确认配置」「重新生成」「修改参数」。
- 用户可修改部分参数（如最大深度、排除路径）。
- 确认后提交后台爬取任务（调用 `POST /api/rag/crawler/task`）。

#### 4.2.4 任务进度与结果模块

- 当前任务实时进度条：轮询 `GET /api/rag/crawler/task/{task_id}`。
- 任务状态展示：`PENDING` / `RUNNING` / `COMPLETED` / `FAILED`。
- 成功页面数 / 失败页面数展示。
- 当前执行步骤提示。
- 历史爬取任务列表。
- 任务详情弹窗。
- 爬取结果文档列表（调用 `GET /api/rag/crawler/document/list`）。
- Markdown 文档预览。
- 文档下载。
- 失败 URL 明细查看（调用 `GET /api/rag/crawler/task/{task_id}/failed-urls`）。
- 任务失败原因提示与重试入口。

### 4.3 页面流转逻辑

1. 用户进入「网页爬虫」页面，默认展示最新会话或空状态。
2. 新建会话后，右侧聊天区显示系统欢迎语（`system` 消息）。
3. 用户输入目标网站意图，前端发送消息并开启 SSE。
4. Agent 返回配置摘要卡片，前端渲染策略确认组件。
5. 用户确认后，前端调用提交任务接口，任务进入 `PENDING`。
6. 前端轮询任务状态，展示进度条与步骤。
7. 任务 `COMPLETED` 后，展示结果文档列表，支持预览/下载。
8. 任务 `FAILED` 后，展示失败原因与失败 URL 明细，提供重试入口。

---

## 五、后端接口

接口统一前缀：`/api/rag`

### 5.1 创建会话

- **接口**：`POST /api/rag/crawler/session`
- **核心参数**：
  - `session_title`：会话标题
  - `model_id`：模型 ID
- **执行流程**：
  1. 生成 `session_id`（UUID 或雪花算法字符串）。
  2. 插入 `web_crawler_session`：
     - `session_id` = 生成值
     - `user_id` = 当前用户 ID
     - `session_title` = 入参
     - `model_id` = 入参
     - `status` = `'ACTIVE'`
     - `create_by` / `create_time` / `update_by` / `update_time` 自动填充
     - `del_flag` = `'0'`
  3. 返回 `AjaxResult.success(session_id)`。

### 5.2 会话列表

- **接口**：`GET /api/rag/crawler/session/list`
- **核心参数**：
  - `page_num`：页码
  - `page_size`：每页条数
  - `session_title`：搜索关键词（可选）
- **执行流程**：
  1. 按 `user_id` 与 `del_flag='0'` 过滤。
  2. 若 `session_title` 非空，按标题模糊查询。
  3. 分页查询 `web_crawler_session`，按 `create_time` 降序。
  4. 返回列表与分页信息。

### 5.3 重命名会话

- **接口**：`PUT /api/rag/crawler/session/{session_id}`
- **核心参数**：
  - `session_title`：新标题
- **执行流程**：
  1. 校验会话归属当前用户。
  2. 更新 `web_crawler_session.session_title`。
  3. 更新 `update_by` / `update_time`。

### 5.4 删除会话

- **接口**：`DELETE /api/rag/crawler/session/{session_id}`
- **执行流程**：
  1. 校验会话归属当前用户。
  2. 软删除 `web_crawler_session`：`del_flag='2'`，更新 `update_by` / `update_time`。
  3. 级联软删除 `web_crawler_message`：`del_flag='2'`。

### 5.5 获取历史消息

- **接口**：`GET /api/rag/crawler/session/{session_id}/messages`
- **核心参数**：
  - `page_num`：页码
  - `page_size`：每页条数
- **执行流程**：
  1. 校验会话归属当前用户。
  2. 按 `session_id` 与 `del_flag='0'` 查询 `web_crawler_message`。
  3. 按 `create_time` 升序分页返回。

### 5.6 Agent 对话（SSE）

- **接口**：`POST /api/rag/crawler/chat`
- **Content-Type**：`text/event-stream`
- **核心参数**：
  - `session_id`：会话 ID
  - `content`：用户消息内容
- **执行流程**：
  1. 校验会话归属当前用户且 `status='ACTIVE'`。
  2. 插入 `web_crawler_message`：
     - `session_id` = 入参
     - `role` = `'user'`
     - `content` = 入参
     - `create_by` / `create_time` 自动填充
     - `del_flag` = `'0'`
  3. 读取会话历史消息（`user` / `assistant` / `tool`），构建 LangGraph State。
  4. 流式调用 LangGraph Agent，逐段返回内容给前端。
  5. 完整回复结束后，插入 `web_crawler_message`：
     - `role` = `'assistant'`
     - `content` = 完整回复内容
     - `tool_calls` = 若有工具调用则存 JSON
  6. 若触发工具调用，额外插入 `role='tool'` 的记录，包含 `tool_call_id` 与工具返回结果。

### 5.7 提交爬取任务

- **接口**：`POST /api/rag/crawler/task`
- **核心参数**：
  - `session_id`：会话 ID
  - `message_id`：触发任务的消息 ID
  - `target_url`：目标 URL
  - `crawl_config`：crawl4ai 配置 JSON
- **执行流程**：
  1. 生成 `task_id`（建议 `crawl_` 前缀 + UUID）。
  2. 插入 `crawl_task`：
     - `task_id` = 生成值
     - `target_url` = 入参
     - `crawl_config` = 入参
     - `status` = `'PENDING'`
     - `progress` = `0`
     - `success_count` = `0`
     - `failed_count` = `0`
     - `create_by` / `create_time` / `update_by` / `update_time` 自动填充
     - `del_flag` = `'0'`
  3. 插入 `web_crawler_session_task`：
     - `session_id` = 入参
     - `task_id` = 生成值
     - `relation_type` = `'creator'`
  4. 插入 `web_crawler_message_task`：
     - `message_id` = 入参
     - `task_id` = 生成值
     - `relation_type` = `'creator'`
  5. 发布后台任务开始爬取（直接调用异步任务或消息流）。
  6. 返回 `AjaxResult.success(task_id)`。

### 5.8 查询爬取任务

- **接口**：`GET /api/rag/crawler/task/{task_id}`
- **执行流程**：
  1. 查询 `crawl_task` 状态、进度、`current_step`、成功/失败数、错误信息。
  2. 返回任务快照。

### 5.9 失败 URL 列表

- **接口**：`GET /api/rag/crawler/task/{task_id}/failed-urls`
- **核心参数**：
  - `page_num`：页码
  - `page_size`：每页条数
- **执行流程**：
  1. 按 `task_id` 与 `del_flag='0'` 查询 `crawl_task_failed_url`。
  2. 按 `create_time` 降序分页返回。

### 5.10 爬取结果文档列表

- **接口**：`GET /api/rag/crawler/document/list`
- **核心参数**：
  - `task_id`：任务 ID
  - `page_num`：页码
  - `page_size`：每页条数
- **执行流程**：
  1. 按 `task_id` 与 `del_flag='0'` 查询 `knowledge_document`。
  2. 过滤 `source_type='1'`（网页爬取）。
  3. 分页返回文档列表。

---

## 六、消费者与定时任务

### 6.1 爬取任务执行器

- **类型**：后台异步任务 / 消费者
- **触发方式**：接口 `POST /api/rag/crawler/task` 提交后直接触发，或消费消息流中的 `crawler.task.pending`
- **核心流程**：
  1. 读取 `crawl_task.crawl_config` 与 `target_url`。
  2. 更新 `crawl_task.status='RUNNING'`，`started_time=NOW()`。
  3. 使用 crawl4ai 执行整站爬取：
     - 固定参数：`headless=True`、`viewport=1920x1080`、`enable_stealth=True`、`user_agent_mode='random'`、`cache_mode=ENABLED`、`stream=True`。
  4. 每爬取一页，更新 `crawl_task.progress`、`current_step`、`success_count`、`failed_count`。
  5. 单页失败时：
     - 记录 `crawl_task_failed_url`（`url`、`error_code`、`error_message`、`retry_count`）。
     - 对 transient 错误尝试重试，更新 `retry_count`。
  6. 全部完成后：
     - 将 Markdown 写入 MinIO。
     - 处理图片等媒体文件上传 MinIO 并替换链接。
     - 创建 `knowledge_document`：
       - `task_id` = 当前任务 ID
       - `source_type` = `'1'`
       - `source_url` = 目标 URL
       - `doc_url` = Markdown URL
       - `status` = `'CONVERTED'`
       - `is_latest` = `'1'`
       - 同标题旧版本 `is_latest='0'`
     - 更新 `crawl_task.status='COMPLETED'`，`progress=100`，`completed_time=NOW()`。
  7. 整体失败时：
     - 更新 `crawl_task.status='FAILED'`。
     - 写入 `error_code` / `error_message`。

### 6.2 爬取任务状态兜底定时任务

- **类型**：定时任务
- **触发方式**：每分钟扫描一次
- **核心流程**：
  1. 扫描 `status='RUNNING'` 且长时间未更新的 `crawl_task`。
  2. 若判定为卡死或浏览器崩溃，将任务状态回退为 `PENDING` 或标记为 `FAILED`。
  3. 支持重新拉起任务（利用 `CacheMode.ENABLED` 减少重复请求）。

---

## 七、数据库表结构

### 7.1 表模块归属

| 表名 | 归属项目 | 说明 |
|------|---------|------|
| `crawl_task` | `knowledge-rag` | 网页爬取任务表 |
| `crawl_task_failed_url` | `knowledge-rag` | 爬取失败 URL 明细表 |
| `web_crawler_session` | `knowledge-rag` | Agent 会话表 |
| `web_crawler_message` | `knowledge-rag` | Agent 消息表 |
| `web_crawler_session_task` | `knowledge-rag` | 会话与任务关联表 |
| `web_crawler_message_task` | `knowledge-rag` | 消息与任务关联表 |
| `knowledge_document` | `knowledge-common` | 文档主表，爬取成功后生成 |

### 7.2 ER 图

```mermaid
erDiagram
    KNOWLEDGE_DOCUMENT {
        bigint doc_id PK "文档主键"
        varchar task_id FK "关联爬取任务ID"
        varchar doc_title "文档标题"
        varchar doc_desc "文档描述"
        varchar doc_name "文件名"
        varchar doc_type "文档格式"
        char source_type "来源类型 0手动上传 1网页爬取"
        text source_url "网页来源URL"
        varchar doc_url "最终Markdown URL"
        varchar doc_version "文档版本 默认1.0"
        char is_latest "是否最新版本 0否1是"
        varchar version_remark "版本说明"
        char is_partial "是否部分解析 0否1是"
        varchar status "文档状态 INIT/UPLOADED/CONVERTED"
        bigint file_size "文件大小 字节"
        int media_count "媒体文件数量"
        bigint user_id "用户ID"
        bigint dept_id "部门ID"
        varchar create_by "创建者"
        datetime create_time "创建时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
        varchar remark "备注"
    }

    CRAWL_TASK {
        varchar task_id PK "任务ID"
        text target_url "目标URL"
        text crawl_config "crawl4ai配置JSON"
        varchar status "任务状态"
        int progress "进度 0-100"
        varchar current_step "当前步骤"
        int success_count "成功页面数"
        int failed_count "失败页面数"
        varchar error_code "错误码"
        text error_message "错误信息"
        datetime started_time "开始时间"
        datetime completed_time "完成时间"
        varchar create_by "创建者"
        datetime create_time "创建时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
        varchar remark "备注"
    }

    CRAWL_TASK_FAILED_URL {
        bigint failed_id PK "失败记录ID"
        varchar task_id FK "关联任务ID"
        text url "失败URL"
        varchar error_code "错误码"
        text error_message "错误信息"
        int retry_count "重试次数"
        varchar create_by "创建者"
        datetime create_time "创建时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
    }

    WEB_CRAWLER_SESSION {
        varchar session_id PK "会话ID"
        bigint user_id "用户ID"
        varchar session_title "会话标题"
        bigint model_id "模型ID"
        varchar status "会话状态"
        varchar create_by "创建者"
        datetime create_time "创建时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
        varchar remark "备注"
    }

    WEB_CRAWLER_MESSAGE {
        bigint message_id PK "消息ID"
        varchar session_id FK "关联会话ID"
        varchar role "角色 user assistant system tool"
        longtext content "消息内容"
        text tool_calls "工具调用JSON"
        varchar tool_call_id "工具调用ID"
        varchar create_by "创建者"
        datetime create_time "创建时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
    }

    WEB_CRAWLER_SESSION_TASK {
        bigint id PK "关联ID"
        varchar session_id FK "会话ID"
        varchar task_id FK "任务ID"
        varchar relation_type "关系类型 creator/reference"
        varchar create_by "创建者"
        datetime create_time "关联时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
    }

    WEB_CRAWLER_MESSAGE_TASK {
        bigint id PK "关联ID"
        bigint message_id FK "消息ID"
        varchar task_id FK "任务ID"
        varchar relation_type "关系类型 creator/reference"
        varchar create_by "创建者"
        datetime create_time "关联时间"
        varchar update_by "更新者"
        datetime update_time "更新时间"
        char del_flag "删除标志 0未删除 2已删除"
    }

    CRAWL_TASK ||--|| KNOWLEDGE_DOCUMENT : "爬取成功后生成"
    CRAWL_TASK ||--o{ CRAWL_TASK_FAILED_URL : "记录失败URL"
    WEB_CRAWLER_SESSION ||--o{ WEB_CRAWLER_MESSAGE : "包含消息"
    WEB_CRAWLER_SESSION ||--o{ WEB_CRAWLER_SESSION_TASK : ""
    CRAWL_TASK ||--o{ WEB_CRAWLER_SESSION_TASK : ""
    WEB_CRAWLER_MESSAGE ||--o{ WEB_CRAWLER_MESSAGE_TASK : ""
    CRAWL_TASK ||--o{ WEB_CRAWLER_MESSAGE_TASK : ""
```

### 7.3 MySQL 建表语句

#### 7.3.1 knowledge_document

```sql
CREATE TABLE `knowledge_document` (
    `doc_id` bigint NOT NULL AUTO_INCREMENT COMMENT '文档主键',
    `log_id` bigint DEFAULT NULL COMMENT '关联上传日志ID（手动上传时）',
    `parse_task_id` bigint DEFAULT NULL COMMENT '关联MinerU解析任务ID（手动上传时）',
    `task_id` varchar(64) DEFAULT NULL COMMENT '关联爬取任务ID（网页爬取时）',
    `doc_title` varchar(255) NOT NULL COMMENT '文档标题',
    `doc_desc` varchar(500) DEFAULT NULL COMMENT '文档描述',
    `doc_name` varchar(255) DEFAULT NULL COMMENT '文件名',
    `doc_type` varchar(50) DEFAULT NULL COMMENT '文档格式 PDF/DOCX/XLSX/TXT/MD',
    `source_type` char(1) DEFAULT '0' COMMENT '来源类型（0-手动上传 1-网页爬取）',
    `source_url` text COMMENT '网页来源URL',
    `original_doc_url` varchar(500) DEFAULT NULL COMMENT '原始上传文件URL（网页爬取时为空）',
    `doc_url` varchar(500) DEFAULT NULL COMMENT '最终Markdown URL',
    `doc_version` varchar(20) DEFAULT '1.0' COMMENT '文档版本',
    `is_latest` char(1) DEFAULT '1' COMMENT '是否最新版本（0-否 1-是）',
    `version_remark` varchar(255) DEFAULT NULL COMMENT '版本说明',
    `is_partial` char(1) DEFAULT '0' COMMENT '是否部分解析（0-否 1-是）',
    `status` varchar(20) DEFAULT 'INIT' COMMENT '文档状态 INIT/UPLOADED/CONVERTED',
    `file_size` bigint DEFAULT '0' COMMENT '文件大小（字节）',
    `media_count` int DEFAULT '0' COMMENT '媒体文件数量',
    `user_id` bigint NOT NULL COMMENT '上传用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`doc_id`),
    UNIQUE KEY `uk_doc_title_version` (`doc_title`, `doc_version`),
    KEY `idx_doc_title` (`doc_title`),
    KEY `idx_source_type` (`source_type`),
    KEY `idx_is_latest` (`is_latest`),
    KEY `idx_log_id` (`log_id`),
    KEY `idx_parse_task_id` (`parse_task_id`),
    KEY `idx_task_id` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档主表';
```

#### 7.3.2 crawl_task

```sql
CREATE TABLE `crawl_task` (
    `task_id` varchar(64) NOT NULL COMMENT '任务ID',
    `target_url` text COMMENT '目标URL',
    `crawl_config` text COMMENT 'crawl4ai配置JSON',
    `status` varchar(20) DEFAULT 'PENDING' COMMENT '任务状态',
    `progress` int DEFAULT '0' COMMENT '进度 0-100',
    `current_step` varchar(50) DEFAULT NULL COMMENT '当前步骤',
    `success_count` int DEFAULT '0' COMMENT '成功页面数',
    `failed_count` int DEFAULT '0' COMMENT '失败页面数',
    `error_code` varchar(50) DEFAULT NULL COMMENT '错误码',
    `error_message` text COMMENT '错误信息',
    `started_time` datetime DEFAULT NULL COMMENT '开始时间',
    `completed_time` datetime DEFAULT NULL COMMENT '完成时间',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`task_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网页爬取任务表';
```

#### 7.3.3 crawl_task_failed_url

```sql
CREATE TABLE `crawl_task_failed_url` (
    `failed_id` bigint NOT NULL AUTO_INCREMENT COMMENT '失败记录ID',
    `task_id` varchar(64) NOT NULL COMMENT '关联任务ID',
    `url` text COMMENT '失败URL',
    `error_code` varchar(50) DEFAULT NULL COMMENT '错误码',
    `error_message` text COMMENT '错误信息',
    `retry_count` int DEFAULT '0' COMMENT '重试次数',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    PRIMARY KEY (`failed_id`),
    KEY `idx_task_id` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爬取失败URL明细表';
```

#### 7.3.4 web_crawler_session

```sql
CREATE TABLE `web_crawler_session` (
    `session_id` varchar(64) NOT NULL COMMENT '会话ID',
    `user_id` bigint NOT NULL COMMENT '用户ID',
    `session_title` varchar(255) DEFAULT NULL COMMENT '会话标题',
    `model_id` bigint DEFAULT NULL COMMENT '模型ID',
    `status` varchar(20) DEFAULT 'ACTIVE' COMMENT '会话状态',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`session_id`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent会话表';
```

#### 7.3.5 web_crawler_message

```sql
CREATE TABLE `web_crawler_message` (
    `message_id` bigint NOT NULL AUTO_INCREMENT COMMENT '消息ID',
    `session_id` varchar(64) NOT NULL COMMENT '关联会话ID',
    `role` varchar(20) DEFAULT NULL COMMENT '角色 user/assistant/system/tool',
    `content` longtext COMMENT '消息内容',
    `tool_calls` text COMMENT '工具调用JSON',
    `tool_call_id` varchar(64) DEFAULT NULL COMMENT '工具调用ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    PRIMARY KEY (`message_id`),
    KEY `idx_session_id` (`session_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent消息表';
```

#### 7.3.6 web_crawler_session_task

```sql
CREATE TABLE `web_crawler_session_task` (
    `id` bigint NOT NULL AUTO_INCREMENT COMMENT '关联ID',
    `session_id` varchar(64) NOT NULL COMMENT '会话ID',
    `task_id` varchar(64) NOT NULL COMMENT '任务ID',
    `relation_type` varchar(20) DEFAULT 'creator' COMMENT '关系类型 creator/reference',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_session_task` (`session_id`, `task_id`),
    KEY `idx_task_id` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='会话与任务关联表';
```

#### 7.3.7 web_crawler_message_task

```sql
CREATE TABLE `web_crawler_message_task` (
    `id` bigint NOT NULL AUTO_INCREMENT COMMENT '关联ID',
    `message_id` bigint NOT NULL COMMENT '消息ID',
    `task_id` varchar(64) NOT NULL COMMENT '任务ID',
    `relation_type` varchar(20) DEFAULT 'creator' COMMENT '关系类型 creator/reference',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-删除）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_message_task` (`message_id`, `task_id`),
    KEY `idx_task_id` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='消息与任务关联表';
```

---

## 八、其他说明

### 8.1 前端 API 代理

前端需新增 `knowledge-rag` 代理入口：

- 开发环境：`/dev-rag-api` → `http://127.0.0.1:9098`
- 生产/容器环境：`/docker-rag-api/` → `knowledge-rag:9098`

### 8.2 兼容性改造

1. `ai_models` 的 DO/DAO/VO 从 `knowledge-admin` 下沉至 `knowledge-common`，`knowledge-admin` 业务代码仅调整 import 路径。
2. 前端 `vite.config.js` 与 nginx 配置新增 `knowledge-rag` 代理。
3. `knowledge-rag` 新增接口的权限编码需在 `knowledge-admin` 菜单/接口权限中注册。

### 8.3 部署依赖

- 运行环境需安装 Playwright + Chromium。
- Docker 镜像需额外处理浏览器运行依赖（如 `libnss3`、`libatk-bridge2.0-0` 等）。

### 8.4 技术栈

- `crawl4ai >= 0.8.9`
- `langchain >= 1.2.15, < 2.0.0`
- `langchain-openai >= 1.1.13, < 2.0.0`
- `langgraph >= 1.1.6, < 2.0.0`
