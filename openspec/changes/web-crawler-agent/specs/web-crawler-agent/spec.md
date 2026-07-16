## ADDED Requirements

### Requirement: Agent 会话管理
系统 SHALL 提供 Agent 会话的完整生命周期管理，包括创建、查询、重命名、删除会话，以及会话状态管理。

#### Scenario: 创建新会话
- **WHEN** 用户请求创建新会话
- **THEN** 系统创建 `web_crawler_session` 记录，状态为 `ACTIVE`，返回会话 ID

#### Scenario: 查询会话列表
- **WHEN** 用户请求查询会话列表
- **THEN** 系统分页返回当前用户的会话列表，支持按标题搜索，按创建时间倒序排列

#### Scenario: 重命名会话
- **WHEN** 用户请求重命名会话
- **THEN** 系统更新 `web_crawler_session.session_title` 字段

#### Scenario: 删除会话
- **WHEN** 用户请求删除会话
- **THEN** 系统级联软删除会话及其关联的消息记录（`web_crawler_message.del_flag='2'`）

#### Scenario: 会话状态管理
- **WHEN** 会话创建时
- **THEN** 状态默认为 `ACTIVE`
- **WHEN** 用户主动关闭会话或长时间未操作
- **THEN** 状态更新为 `CLOSED`

### Requirement: Agent 消息存储
系统 SHALL 存储会话中的所有消息，支持 user、assistant、system、tool 四种角色。

#### Scenario: 存储用户消息
- **WHEN** 用户发送消息
- **THEN** 系统创建 `web_crawler_message` 记录，`role='user'`，`content` 为消息内容

#### Scenario: 存储 AI 回复
- **WHEN** Agent 完整回复结束
- **THEN** 系统创建 `web_crawler_message` 记录，`role='assistant'`，`content` 为回复内容

#### Scenario: 存储工具调用结果
- **WHEN** Agent 调用分析工具
- **THEN** 系统创建 `web_crawler_message` 记录，`role='tool'`，`content` 为工具返回的 JSON，`tool_call_id` 为工具调用 ID

#### Scenario: 存储系统提示
- **WHEN** 会话初始化或系统通知时
- **THEN** 系统创建 `web_crawler_message` 记录，`role='system'`，`content` 为系统提示内容

#### Scenario: 获取历史消息
- **WHEN** 用户请求获取会话历史消息
- **THEN** 系统分页返回该会话的所有消息，按创建时间升序排列

### Requirement: Agent 对话 SSE 流式响应
系统 SHALL 提供 SSE 流式响应接口，支持 Agent 与用户的实时对话。

#### Scenario: 发送消息并获取流式响应
- **WHEN** 用户发送消息
- **THEN** 系统将用户消息入库，并返回 SSE 流，实时推送 Agent 的 token 输出、工具调用过程和最终回复

#### Scenario: SSE 事件类型
- **WHEN** Agent 生成回复时
- **THEN** 系统推送 `token` 事件（逐 token 输出）、`tool_call` 事件（工具调用开始）、`tool_result` 事件（工具调用结果）、`done` 事件（回复完成，包含 message_id）

#### Scenario: 中断 SSE 连接
- **WHEN** 用户中断 SSE 连接
- **THEN** 系统停止生成，已接收内容可选择性保存为不完整 `assistant` 消息

### Requirement: 站点分析工具链
系统 SHALL 提供 5 个分析工具，用于自动分析目标站点特征。

#### Scenario: fetch_robots_txt 工具
- **WHEN** Agent 调用 `fetch_robots_txt` 工具
- **THEN** 系统获取目标站点的 robots.txt，解析允许/禁止爬取路径、Sitemap 地址、爬取延迟，返回结构化 JSON

#### Scenario: fetch_sitemap 工具
- **WHEN** Agent 调用 `fetch_sitemap` 工具
- **THEN** 系统获取目标站点的 sitemap.xml，统计 URL 总量、按路径前缀分组计数、抽样代表性 URL，返回结构化 JSON

#### Scenario: fetch_page 工具
- **WHEN** Agent 调用 `fetch_page` 工具
- **THEN** 系统抓取单页面，分析页面结构、链接分布、分页模式、JS 渲染特征、弹窗类型，返回结构化 JSON

#### Scenario: test_anti_crawling 工具
- **WHEN** Agent 调用 `test_anti_crawling` 工具
- **THEN** 系统检测目标站点反爬机制等级（轻度/中度/高度）、是否需要 JS 渲染、是否有验证码、是否限速，返回结构化 JSON

#### Scenario: analyze_url_patterns 工具
- **WHEN** Agent 调用 `analyze_url_patterns` 工具
- **THEN** 系统分析 URL 列表的路径模式，归纳目录结构与内容分类，推断推荐爬取深度，返回结构化 JSON

### Requirement: 策略生成与确认
系统 SHALL 基于站点分析结果与用户回答，生成完整的 crawl4ai 爬取策略配置，并支持用户确认。

#### Scenario: 分类收集用户意图
- **WHEN** Agent 完成站点分析后
- **THEN** Agent 按七大配置主题归类，向用户发起业务导向的提问，收集第二类参数（爬取范围、内容维度、页面数量、媒体下载等）

#### Scenario: 生成策略配置摘要
- **WHEN** 用户回答所有问题后
- **THEN** Agent 生成完整的 crawl4ai 策略配置摘要，按七大配置主题分组展示，每个参数标注来源标签（「用户选择」「自动适配」「固定默认」）

#### Scenario: 用户确认策略
- **WHEN** 用户点击「确认配置」
- **THEN** 系统将策略配置提交为后台爬取任务，返回任务 ID

#### Scenario: 用户重新生成策略
- **WHEN** 用户点击「重新生成」
- **THEN** Agent 重新推理生成新的策略配置，消耗 1 次 LLM 调用

#### Scenario: 用户修改参数
- **WHEN** 用户点击「修改参数」
- **THEN** 系统将配置摘要渲染为可编辑表单，用户可修改第二类参数，修改后重新展示摘要供确认

### Requirement: 爬取任务提交
系统 SHALL 提供爬取任务提交接口，将用户确认的策略配置提交为后台异步任务。

#### Scenario: 提交爬取任务
- **WHEN** 用户确认策略配置
- **THEN** 系统创建 `crawl_task` 记录，状态为 `PENDING`，关联会话和消息，返回任务 ID

#### Scenario: 重复爬取限制
- **WHEN** 当前会话已存在该 URL 的成功爬取记录（状态为 `COMPLETED` / `CONVERTED`）
- **THEN** 系统提示用户「该网址已在本会话中爬取成功，请新建聊天框处理」，不允许重复提交任务

### Requirement: 爬取任务执行
系统 SHALL 后台异步执行 crawl4ai 爬取任务，实时更新任务进度。

#### Scenario: 任务开始执行
- **WHEN** 后台 Worker 获取到待执行任务
- **THEN** 系统更新 `crawl_task.status='RUNNING'`，`started_time=NOW()`

#### Scenario: 任务进度更新
- **WHEN** 每爬取一页
- **THEN** 系统更新 `crawl_task.progress`、`current_step`、`success_count`、`failed_count`

#### Scenario: 任务执行成功
- **WHEN** 爬取完成且结果处理成功
- **THEN** 系统更新 `crawl_task.status='COMPLETED'`，`progress=100`，`completed_time=NOW()`

#### Scenario: 任务执行失败
- **WHEN** 爬取失败或结果处理失败
- **THEN** 系统更新 `crawl_task.status='FAILED'`，写入 `error_code`、`error_message`，记录 `crawl_task_failed_url`

### Requirement: 失败自动修复机制
系统 SHALL 在任务失败时执行分层自动修复策略。

#### Scenario: 规则自动重试
- **WHEN** 任务失败且错误类型可由规则判定（浏览器崩溃、页面超时、连接重置、429 限速、403/Cloudflare 挑战）
- **THEN** Worker 自动调整参数重试，最多重试 3 次

#### Scenario: 静默调用 LLM 修复
- **WHEN** 规则重试用尽且失败原因为复杂场景
- **THEN** Worker 静默调用 Agent LLM 分析失败原因，返回参数调整建议，最多重试 1 次

#### Scenario: 升级为用户决策
- **WHEN** 自动修复用尽且失败原因为用户确认的参数问题
- **THEN** 任务状态更新为 `USER_DECISION`，通过消息流通知前端

#### Scenario: 直接标记失败
- **WHEN** 自动修复用尽且失败原因为 Agent/默认参数问题
- **THEN** 任务状态更新为 `FAILED`，不打扰用户

### Requirement: 用户决策处理
系统 SHALL 在任务进入 `USER_DECISION` 状态时，支持用户选择重试或放弃。

#### Scenario: 用户选择重试
- **WHEN** 用户选择「调整参数重试」
- **THEN** 系统将任务状态更新为 `PENDING`，用户可修改 `crawl_config` 后重新执行

#### Scenario: 用户选择放弃
- **WHEN** 用户选择「放弃删除」
- **THEN** 系统逻辑删除任务（`crawl_task.del_flag='2'`）

### Requirement: 文档落库
系统 SHALL 将爬取成功的 Markdown 结果写入 MinIO，并创建 `knowledge_document` 记录。

#### Scenario: Markdown 写入 MinIO
- **WHEN** 爬取任务完成
- **THEN** 系统将爬取结果 Markdown 写入 MinIO，处理图片等媒体文件上传并替换链接

#### Scenario: 创建文档记录
- **WHEN** Markdown 写入 MinIO 成功
- **THEN** 系统创建 `knowledge_document` 记录，`task_id` 关联爬取任务，`source_type='1'`（网页爬取），`source_url` 为目标 URL，`doc_key` 为 MinIO 对象键，`status='CONVERTED'`

#### Scenario: 版本管理
- **WHEN** 创建文档记录时
- **THEN** 系统调用版本号预生成接口获取新版本号，写入 `doc_version` 字段，并更新该标题其他未删除记录的 `is_latest='0'`

### Requirement: 爬取任务查询
系统 SHALL 提供爬取任务查询接口，返回任务状态、进度、统计信息。

#### Scenario: 查询任务详情
- **WHEN** 前端请求查询任务详情
- **THEN** 系统返回 `crawl_task` 的状态、进度、当前步骤、成功/失败页面数、错误信息等

#### Scenario: 查询失败 URL 列表
- **WHEN** 前端请求查询失败 URL 列表
- **THEN** 系统分页返回 `crawl_task_failed_url` 记录，包含 URL、错误码、错误信息、重试次数

### Requirement: 爬取结果文档列表
系统 SHALL 提供爬取结果文档列表查询接口。

#### Scenario: 查询文档列表
- **WHEN** 前端请求查询爬取结果文档列表
- **THEN** 系统分页返回该任务关联的 `knowledge_document` 记录，包含文档标题、文件名、版本号、状态等

#### Scenario: 文档预览
- **WHEN** 用户点击文档「预览」按钮
- **THEN** 系统从 MinIO 读取 Markdown 内容并返回

#### Scenario: 文档下载
- **WHEN** 用户点击文档「下载」按钮
- **THEN** 系统从 MinIO 下载 Markdown 文件并以流形式返回

### Requirement: 前端网页爬虫页面
系统 SHALL 在「知识管理」菜单下新增「网页爬虫」独立页面。

#### Scenario: 页面布局
- **WHEN** 用户进入「知识管理 → 网页爬虫」页面
- **THEN** 系统展示「左侧会话列表 + 右侧聊天区」两栏布局

#### Scenario: 会话列表区
- **WHEN** 页面加载时
- **THEN** 系统展示会话列表，支持新建会话、搜索会话、点击会话加载历史消息

#### Scenario: 聊天消息区
- **WHEN** 用户与 Agent 对话时
- **THEN** 系统展示消息气泡（user 右对齐、assistant 左对齐、system 居中、tool 折叠卡片），支持 Markdown 渲染、工具调用可视化

#### Scenario: 策略确认卡片
- **WHEN** Agent 生成策略配置后
- **THEN** 系统展示策略确认卡片，包含目标 URL、配置摘要、操作按钮（确认配置、重新生成、修改参数）

#### Scenario: 任务进度区
- **WHEN** 爬取任务执行中
- **THEN** 系统展示任务进度卡片，包含状态标签、进度条、当前步骤、统计数据，支持轮询更新

#### Scenario: 文档列表与预览
- **WHEN** 爬取任务完成
- **THEN** 系统展示文档列表卡片，支持预览、下载 Markdown 文件

### Requirement: Agent 架构实现
系统 SHALL 采用 ReAct + Reflection + Human-in-the-Loop 组合架构实现 Agent。

#### Scenario: ReAct 循环
- **WHEN** 用户发送目标 URL
- **THEN** Agent 执行 ReAct 循环（最多 3 轮），调用分析工具链，根据工具返回动态决策下一步

#### Scenario: Reflection 自审
- **WHEN** ReAct 循环结束
- **THEN** Agent 执行 Reflection 自审，判断分析结果是否充分，不足则追问用户

#### Scenario: Human-in-the-Loop
- **WHEN** 策略配置生成后
- **THEN** Agent 进入 Human-in-the-Loop 中断点，等待用户确认、重新生成或修改参数

### Requirement: 数据压缩与成本控制
系统 SHALL 实现三层数据压缩方案，控制 LLM 调用成本。

#### Scenario: 工具内部压缩
- **WHEN** 分析工具返回结果时
- **THEN** 工具自行完成「原始数据 → 结构化结论」的精炼，单轮工具总计 ≤ 1,900 tokens

#### Scenario: 对话历史压缩
- **WHEN** 构建 LLM 上下文时
- **THEN** 系统过滤掉 `role='tool'` 的消息，只保留 `user` / `assistant` 消息，滑动窗口 + 历史摘要，对话历史总计 ≤ 4,000 tokens

#### Scenario: Token 预算管控
- **WHEN** 单轮对话时
- **THEN** 系统确保单轮总消耗 ≤ 10,000 tokens，含所有输入输出