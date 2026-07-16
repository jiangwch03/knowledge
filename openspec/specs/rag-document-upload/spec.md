## Purpose

规范知识库资料上传、MinerU 文档解析、TX T转 Markdown、版本管理及前后端交互流程。覆盖文件上传、解析任务调度、状态兜底、用户决策、文档落库与预览下载全生命周期。

## Requirements

### Requirement: 前端新增资料上传主页面（参考需求文档 §4.1 / §4.2）
系统 SHALL 在「知识管理」菜单下新增「资料上传」独立页面，页面包含顶部操作区与文档列表。

#### Scenario: 进入资料上传主页面
- **WHEN** 用户进入「知识管理 → 资料上传」页面
- **THEN** 系统展示文档列表，并提供「上传文件」与「Markdown 转换」按钮

### Requirement: 文档列表展示与筛选（参考需求文档 §4.2.2 / §4.2.3）
系统 SHALL 按 `knowledge_upload_document_record` 为主表展示文档列表，默认按 `update_time` 倒序排列，仅展示每个标题的最新版本（`is_latest='1'`）。

#### Scenario: 默认展示最新版本文档列表
- **WHEN** 用户进入资料上传主页面
- **THEN** 系统默认展示当前用户已上传/生成的最新版本文档，字段包括文档标题、文档格式、文档描述、版本、状态与操作

#### Scenario: 按条件筛选文档列表
- **WHEN** 用户输入文档标题、文档描述、选择文档格式或状态并查询
- **THEN** 系统按条件过滤并分页返回文档列表

### Requirement: 列表行内操作权限控制（参考需求文档 §4.2.2）
系统 SHALL 根据上传记录状态动态展示预览、下载、删除、查看解析任务操作。

#### Scenario: CONVERTED 状态展示预览与下载
- **WHEN** 上传记录状态为 `CONVERTED`
- **THEN** 系统展示「预览」与「下载」按钮

#### Scenario: 非 CONVERTED 状态允许删除
- **WHEN** 上传记录状态不为 `CONVERTED` 且尚未生成 `knowledge_document`
- **THEN** 系统展示「删除」按钮

### Requirement: 文件上传弹框（参考需求文档 §4.3）
系统 SHALL 提供文件上传弹框，支持文件选择、参数配置与同名版本提示。

#### Scenario: 打开上传弹框
- **WHEN** 用户点击「上传文件」按钮
- **THEN** 系统弹出上传表单弹框，支持选择 PDF/DOCX/XLSX/MD 文件

#### Scenario: PDF/DOCX 文件显示解析参数
- **WHEN** 用户选择 PDF/DOCX/XLSX 文件
- **THEN** 系统展示解析模式、公式识别、表格识别、文档语言、OCR 配置项

#### Scenario: MD 文件隐藏解析参数
- **WHEN** 用户选择 MD 文件
- **THEN** 系统隐藏解析参数配置项

#### Scenario: 同名文档版本提示
- **WHEN** 用户输入已存在的文档标题
- **THEN** 系统提示下一版本号（如「将创建版本 2.0」）

### Requirement: 文件上传后端接口（参考需求文档 §5.1 / §6.1）
系统 SHALL 提供 `POST /api/rag/document/upload` 接口，支持 MD 直接落库，PDF/DOCX/XLSX 创建 MinerU 解析任务。

#### Scenario: 上传 MD 文件直接入库
- **WHEN** 用户上传 MD 文件
- **THEN** 系统将文件保存至 MinIO，预占版本号，创建上传记录并直接生成 `knowledge_document`，上传记录状态更新为 `CONVERTED`

#### Scenario: 上传 PDF/DOCX 文件创建解析任务
- **WHEN** 用户上传 PDF/DOCX/XLSX 文件
- **THEN** 系统将文件保存至 MinIO，解析总页数，预占版本号，创建上传记录与 `knowledge_mineru_parse_task`，状态为 `PENDING`，并发布 `document.parse.pending` 消息

#### Scenario: 上传不支持的文件类型
- **WHEN** 用户上传非 PDF/DOCX/XLSX/MD 文件
- **THEN** 系统返回文件类型校验错误

### Requirement: TXT 生成 Markdown 格式文档（参考需求文档 §4.4 / §5.2）
系统 SHALL 提供 `POST /api/rag/document/txt/convert` 接口，将 UTF-8 文本转换为大模型生成的 Markdown。

#### Scenario: 正常转换 TXT 为 Markdown
- **WHEN** 前端传入不超过 512KB 的 UTF-8 文本
- **THEN** 系统通过参数 ID `txt_to_markdown` 读取大模型配置并调用大模型，返回结构化的 Markdown 内容

#### Scenario: 文本超过大小限制
- **WHEN** 前端传入文本折算大小超过 512KB
- **THEN** 系统返回错误，提示用户拆分或手动处理

### Requirement: 解析任务查询（参考需求文档 §5.3 / §4.5.1）
系统 SHALL 提供 `GET /api/rag/document/parse-task/{parse_task_id}` 接口，返回解析任务状态与错误信息。

#### Scenario: 查询解析任务快照
- **WHEN** 前端请求解析任务详情
- **THEN** 系统返回 `knowledge_mineru_parse_task` 的状态、错误码与错误信息

### Requirement: 解析分段明细查询（参考需求文档 §5.4 / §4.5.2）
系统 SHALL 提供 `GET /api/rag/document/parse-task/{parse_task_id}/details` 接口，分页返回分段明细。

#### Scenario: 查询分段明细
- **WHEN** 前端请求解析任务的分段明细
- **THEN** 系统按 `sequence_number` 升序分页返回各分段的 `sequence_number`、`state`、`page_ranges`

### Requirement: 用户决策重试或删除（参考需求文档 §5.5 / §4.5.3）
系统 SHALL 提供 `POST /api/rag/document/parse-task/{parse_task_id}/decision` 接口，支持 `retry` 或 `delete`。

#### Scenario: 用户选择重试
- **WHEN** 解析任务状态为 `FAILED` 且上传记录状态为 `USER_DECISION`，用户选择重试
- **THEN** 系统将旧解析任务状态更新为 `COMPLETED`，旧失败分段状态更新为 `RETRIED`，对失败分段新建解析任务并发布 `document.parse.pending`，上传记录状态更新为 `PENDING`

#### Scenario: 用户选择删除
- **WHEN** 用户选择删除
- **THEN** 系统校验未生成 `knowledge_document` 后，软删除上传记录、解析任务与分段任务

### Requirement: 文档预览（参考需求文档 §5.7）
系统 SHALL 提供 `GET /api/rag/document/{doc_id}/preview` 接口，从 MinIO 读取 Markdown 内容并返回。

#### Scenario: 预览已转换文档
- **WHEN** 用户点击已 `CONVERTED` 文档的预览按钮
- **THEN** 系统从 MinIO 读取最终 Markdown 内容并返回文本

### Requirement: 文档下载（参考需求文档 §5.8）
系统 SHALL 提供 `GET /api/rag/document/{doc_id}/download` 接口，以流形式下载 Markdown 文件。

#### Scenario: 下载已转换文档
- **WHEN** 用户点击已 `CONVERTED` 文档的下载按钮
- **THEN** 系统从 MinIO 下载 Markdown 文件并以 `application/octet-stream` 返回

### Requirement: Stage2 消费者申请链接并上传文件（参考需求文档 §6.2）
系统 SHALL 消费 `document.parse.pending` 消息，向 MinerU 申请批量上传链接并上传各分段文件。

#### Scenario: 首次解析生成分段并上传
- **WHEN** 消费者获取到 `parse_task_id` 且该任务无已有分段
- **THEN** 系统根据 `total_pages` 生成 `sequence_number` 与 `page_ranges`，申请 `batch_id`，创建 `knowledge_mineru_parse_detail_task`，并上传各分段

#### Scenario: 申请链接失败进入兜底
- **WHEN** 向 MinerU 申请批量上传链接失败
- **THEN** 系统将解析任务与上传记录状态更新为 `LINK_FAILED`，由 Stage2 定时任务兜底重试

#### Scenario: 上传结果处理
- **WHEN** 所有分段上传完成后
- **THEN** 系统更新分段状态，全部成功则进入 `PARSING`；部分成功则失败分段标记 `UPLOAD_FAILED` 并进入 Stage2 定时任务兜底；全部失败则状态为 `UPLOADING`

### Requirement: Stage2 定时任务兜底上传失败（参考需求文档 §6.3 路径 B）
系统 SHALL 每分钟扫描 `UPLOAD_FAILED` 分段，按 `upload_expire_at` 判断是否过期，未过期则复用现有 `upload_url` 重新上传，已过期则标记为 `PARSE_FAILED`。

#### Scenario: 未过期链接重试上传
- **WHEN** Stage2 定时任务扫描到 `UPLOAD_FAILED` 分段且 `upload_expire_at` 未过期
- **THEN** 系统复用现有 `upload_url` 重新上传该分段

#### Scenario: 链接过期收敛为人工决策态
- **WHEN** 分段 `upload_expire_at` 已过期且该 batch 下所有分段均已超时失败
- **THEN** 系统将分段状态标记为 `PARSE_FAILED`，解析任务状态更新为 `FAILED`，上传记录状态更新为 `USER_DECISION`

### Requirement: Stage3 定时任务轮询解析结果（参考需求文档 §6.4）
系统 SHALL 每分钟扫描 `PARSING` 解析任务，用 `batch_id` 批量轮询 MinerU 解析结果。

#### Scenario: 所有分段解析成功
- **WHEN** Stage3 轮询发现所有分段均解析成功
- **THEN** 系统将分段状态更新为 `PARSED`，解析任务与上传记录状态更新为 `COMPLETED`，并发布 `document.md.pending`

#### Scenario: 存在解析失败分段
- **WHEN** Stage3 轮询发现存在失败分段
- **THEN** 系统将失败分段状态更新为 `PARSE_FAILED`，解析任务状态更新为 `FAILED`，上传记录状态更新为 `USER_DECISION`

### Requirement: Stage4 消费者合并 Markdown 并入库（参考需求文档 §6.5；图片模型由你明确要求为 qwen3-vl-plus）
系统 SHALL 消费 `document.md.pending` 消息，下载 ZIP、合并 Markdown、使用 `qwen3-vl-plus` 模型生成图片描述并替换 Markdown 图片引用、上传最终 Markdown 至 MinIO 并创建 `knowledge_document`。

#### Scenario: md 合并与入库成功
- **WHEN** 消费者获取 `record_id` 且该记录下无进行中的解析任务
- **THEN** 系统下载所有 `PARSED` 分段 ZIP，合并 Markdown，对 ZIP 中提取的图片使用 `qwen3-vl-plus` 模型生成图片描述并替换 Markdown 图片引用，上传最终 Markdown 至 MinIO，创建 `knowledge_document`，上传记录状态更新为 `CONVERTED`

#### Scenario: md 合并异常进入 Stage4 兜底
- **WHEN** md 合并或入库过程出现异常
- **THEN** 系统将上传记录状态更新为 `CONVERT_FAILED`，等待 Stage4 定时任务兜底重试

### Requirement: Stage4 定时任务兜底 md 合并失败（参考需求文档 §6.6）
系统 SHALL 每 5 分钟扫描 `CONVERT_FAILED` 的上传记录，重新发布 `document.md.pending`。

#### Scenario: Stage4 定时任务重新触发合并
- **WHEN** Stage4 定时任务扫描到 `CONVERT_FAILED` 记录
- **THEN** 系统重新发布 `document.md.pending`，持续尝试直至成功或用户删除

### Requirement: 文档版本管理（参考需求文档 §3.5 / §4.3.2 / §5.1 / §6.5）
系统 SHALL 在 `knowledge_upload_document_record` 与 `knowledge_document` 中维护 `doc_version`、`is_latest`、`version_remark`。

#### Scenario: 新版本预占与旧版本降级
- **WHEN** 创建新上传记录时
- **THEN** 系统查询该标题当前最大版本号并递增，预占新版本号，并将同标题其他未删除上传记录的 `is_latest` 更新为 `'0'`

#### Scenario: 文档落库时更新最新版标记
- **WHEN** 创建 `knowledge_document` 时
- **THEN** 系统沿用上传记录版本号，按当前已落库最大版本号动态判断 `is_latest`，若为最新版则将同标题旧版本 `is_latest` 更新为 `'0'`

#### Scenario: 网页爬取文档版本管理
- **WHEN** 爬取任务完成创建 `knowledge_document` 时
- **THEN** 系统复用 `/document-parse/next-version` 接口获取新版本号，写入 `doc_version` 字段，并更新该标题其他未删除记录的 `is_latest='0'`

### Requirement: Markdown 转换页面（参考需求文档 §4.4）
系统 SHALL 提供独立的 Markdown 转换页面，支持上传 TXT 文件或粘贴纯文本生成 Markdown。

#### Scenario: 上传 TXT 并生成 Markdown
- **WHEN** 用户在 Markdown 转换页面上传 TXT 文件
- **THEN** 前端识别文件编码并转换为 UTF-8，展示原始内容

#### Scenario: 保存 Markdown 按 MD 落库
- **WHEN** 用户在编辑器内点击保存
- **THEN** 前端将 Markdown 内容作为文件调用 `POST /api/rag/document/upload` 落库，后端按 MD 文件处理

### Requirement: 数据初始化（参考需求文档 §8.1 / §8.2 / §10.4）
系统 SHALL 在 `knowledge-admin` 中初始化 `merio_language` 字典与 TXT 转 Markdown 所需的大模型及模型功能适配记录。

#### Scenario: 初始化 merio_language 字典
- **WHEN** 系统部署时执行初始化 SQL
- **THEN** `sys_dict_type` 与 `sys_dict_data` 中新增 `merio_language` 相关记录

#### Scenario: 初始化模型功能适配记录
- **WHEN** 系统部署时执行初始化 SQL
- **THEN** `knowledge_ai_models` 与 `knowledge_ai_model_function_adapter` 中新增 `txt_to_markdown` 适配记录
