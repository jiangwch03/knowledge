## 1. 数据库与初始化（参考需求文档 §7 / §8）

- [x] 1.1 新建 `knowledge_document` 表，字段包括 `doc_id`、`record_id`、`source_type`、`doc_title`、`doc_desc`、`doc_name`、`doc_type`、`source_url`、`original_doc_url`、`doc_url`、`doc_version`、`is_latest`、`version_remark`、`status`、`media_count`、`user_id`、`dept_id`、审计字段及索引
- [x] 1.2 新建 `knowledge_upload_document_record` 表及唯一索引 `uk_doc_title_version`、状态索引等
- [x] 1.3 新建 `knowledge_mineru_parse_task` 表及 `record_id`、`status` 索引
- [x] 1.4 新建 `knowledge_mineru_parse_detail_task` 表及 `parse_task_id`、`sequence_number`、`batch_id`、`state` 索引
- [x] 1.5 新建 `knowledge_ai_model_function_adapter` 表及 `uk_param_id`、`idx_model_id` 索引
- [x] 1.6 编写 `merio_language` 字典初始化 SQL
- [x] 1.7 编写 `knowledge_ai_models` 与 `knowledge_ai_model_function_adapter` 初始化 SQL（参数 ID `txt_to_markdown`、图片生成描述参数 ID `md_image_description`）
- [x] 1.8 编写 `qwen3-vl-plus` 模型初始化 SQL，字段结构与 `deepseek-chat` 保持一致

## 2. 公共组件与模型下沉（参考需求文档 §9.2 / §10.2）

- [x] 2.1 在 `knowledge-common` 中创建 `knowledge_ai_models` 的 DO/DAO/VO
- [x] 2.2 在 `knowledge-common` 中创建 `knowledge_ai_model_function_adapter` 的 DO/DAO/VO
- [x] 2.3 在 `knowledge-common` 中引入 LangChain 1.2.X 依赖，并新建大模型调用工厂/工具类，支持根据 `provider`/`base_url`/`api_key`/`model_name` 等参数创建模型实例
- [x] 2.4 调整 `knowledge-admin` 中 `knowledge_ai_models` 的 import 路径至 `knowledge-common`
- [x] 2.5 验证 `knowledge-admin` 原有 AI 模型相关接口编译通过
- [x] 2.6 标记现有基于 agno 的 `AiUtil` 为废弃（或在后续变更中删除），本次不再新增 agno 依赖

## 3. 后端 DO/DAO/VO 与枚举定义（参考需求文档 §3 / §7）

- [x] 3.1 在 `knowledge-content` 中定义上传记录、解析任务、解析分段、文档主表的 DO
- [x] 3.2 在 `knowledge-content` 中定义上述表的 DAO/Mapper
- [x] 3.3 在 `knowledge-content` 中定义状态枚举：`DocumentUploadStatus`、`MineruParseTaskStatus`、`MineruParseDetailState`；在 `knowledge-common` 中定义 `DocumentStatus`，供 `knowledge-content` 与后续分块/向量化模块共享
- [x] 3.4 在 `knowledge-content` 中定义上传、解析、决策、列表查询等 VO

## 4. 文件上传与版本管理接口（参考需求文档 §5.1 / §6.1）

- [x] 4.1 实现 `POST /api/rag/document/upload` 接口：文件校验、MinIO 上传、总页数解析
- [x] 4.2 实现版本预占逻辑：对 `doc_title` 加锁、递增版本号、创建 `knowledge_upload_document_record`
- [x] 4.3 实现 MD 文件直接创建 `knowledge_document` 并更新上传记录状态为 `CONVERTED`
- [x] 4.4 实现 PDF/DOCX/XLSX 创建 `knowledge_mineru_parse_task` 并发布 `document.parse.pending`

## 5. TXT 转 Markdown 与模型功能适配（参考需求文档 §4.4 / §5.2 / §10）

- [x] 5.1 实现 `POST /api/rag/document/txt/convert` 接口：长度校验（512KB）、UTF-8 解析
- [x] 5.2 实现通过参数 ID `txt_to_markdown` 读取模型功能适配配置
- [x] 5.3 使用 LangChain 1.2.X 调用大模型，将纯文本转换为 Markdown 格式内容
- [x] 5.4 在 `knowledge-admin` 中实现模型功能适配 CRUD 接口（列表、新增、修改、删除、按参数 ID 取模型配置）

## 6. 解析任务查询与用户决策（参考需求文档 §5.3 / §5.4 / §5.5 / §5.7 / §5.8 / §5.9 / §5.6）

- [x] 6.1 实现 `GET /api/rag/document/parse-task/{parse_task_id}` 接口
- [x] 6.2 实现 `GET /api/rag/document/parse-task/{parse_task_id}/details` 接口
- [x] 6.3 实现 `POST /api/rag/document/parse-task/{parse_task_id}/decision` 接口（retry/delete）
- [x] 6.4 实现 `GET /api/rag/document/{doc_id}/preview` 接口
- [x] 6.5 实现 `GET /api/rag/document/{doc_id}/download` 接口
- [x] 6.6 实现 `DELETE /api/rag/document/{record_id}` 删除接口（仅允许未落库文档）
- [x] 6.7 实现 `GET /api/rag/document/list` 文档上传记录列表查询接口

## 7. Stage2 申请链接与上传消费者（参考需求文档 §6.2）

- [x] 7.1 实现 `document.parse.pending` 消费者：查询解析任务、校验 `PENDING` 状态
- [x] 7.2 实现按 `total_pages` 分段策略（单分段最多 300 页）
- [x] 7.3 实现 MinerU 批量上传链接申请及失败处理（`LINK_FAILED`）
- [x] 7.4 实现创建/更新 `knowledge_mineru_parse_detail_task`
- [x] 7.5 实现按 `page_ranges` 从原始文件切片并上传至 MinerU 预签名链接
- [x] 7.6 实现上传结果处理逻辑（全部成功/部分成功/全部失败）

## 8. Stage2/Stage3/Stage4 定时任务（参考需求文档 §6.3 / §6.4 / §6.5 / §6.6）

- [x] 8.1 实现 Stage2 定时任务路径 A：扫描 `LINK_FAILED` 任务并重新申请批量上传链接
- [x] 8.2 实现 Stage2 定时任务路径 B：扫描 `UPLOAD_FAILED` 分段，复用现有 `upload_url` 重试；若 `upload_expire_at` 已过期则标记为 `PARSE_FAILED`
- [x] 8.3 实现 Stage2 路径 B 的 batch 失败收敛逻辑（全部超时失败时解析任务 `FAILED`、上传记录 `USER_DECISION`）
- [x] 8.4 实现 Stage3 定时任务：扫描 `PARSING` 任务，批量轮询 MinerU 解析结果
- [x] 8.5 实现 Stage3 全部成功与存在失败情况的状态收敛逻辑
- [x] 8.6 实现 Stage4 消费者：消费 `document.md.pending`，下载 ZIP、合并 Markdown、使用 `qwen3-vl-plus` 模型生成图片描述并替换 Markdown 图片引用、上传最终 Markdown 至 MinIO、创建 `knowledge_document`
- [x] 8.7 实现 Stage4 定时任务：扫描 `CONVERT_FAILED` 记录并重新发布 `document.md.pending`

## 9. 前端资料上传页面（参考需求文档 §4 / §9.1）

- [x] 9.1 在 `knowledge-web` 中新增「知识管理 → 资料上传」菜单与路由
- [x] 9.2 实现资料上传主页面布局（顶部操作区 + 文档列表 + 筛选分页）
- [x] 9.3 实现文档列表字段展示与状态标签
- [x] 9.4 实现上传文件弹框组件（文件选择、参数配置、版本提示）
- [x] 9.5 实现 Markdown 转换页面（TXT 上传/粘贴、编码识别、生成 Markdown、编辑器、下载/保存）
- [x] 9.6 实现解析任务卡片组件（10 秒轮询、分段明细、失败高亮、重试/删除按钮）
- [x] 9.7 实现列表行内操作：预览、下载、删除
- [x] 9.8 新增 `knowledge-content` API 封装与代理配置（vite/nginx）

## 10. 权限与部署配置（参考需求文档 §9.1 / §9.2）

- [x] 10.1 在 `knowledge-admin` 菜单/接口权限中注册 `knowledge-content` 新接口权限编码
- [x] 10.2 配置前端开发环境与生产环境代理（`/dev-rag-api`、`/docker-rag-api/`）
- [x] 10.3 更新 nginx 配置支持 `knowledge-content` 反向代理
- [x] 10.4 验证三端启动脚本（`knowledge-common`、`knowledge-content`、`knowledge-web`）正常

## 11. 测试与验证（参考需求文档 §3 / §5 / §6 状态与接口定义）

- [x] 11.1 编写 MD 文件直接落库接口单元测试
- [x] 11.2 编写 PDF/DOCX 文件上传与解析任务创建单元测试
- [x] 11.3 编写 TXT 转 Markdown 接口单元测试
- [x] 11.4 编写模型功能适配 CRUD 单元测试
- [x] 11.5 编写 Stage2/Stage3/Stage4 状态流转集成测试
- [x] 11.6 前端联调：上传 → 解析 → 入库 → 预览/下载完整流程
- [x] 11.7 验证失败重试、用户决策、删除路径正确性
