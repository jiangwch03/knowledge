## Context

当前知识库数据依赖人工整理，缺少面向 PDF/DOCX/XLSX/TXT/MD 的标准化上传解析通道。RAG 检索增强需要持续补充高质量 Markdown 数据源，因此需要构建一套端到端的资料上传解析系统：前端提供上传页面与 Markdown 转换页面，后端完成文件落库、MinerU 解析、TXT 转 Markdown、版本管理、失败重试与用户决策。

## Goals / Non-Goals

**Goals:**
- 支持 PDF/DOCX/XLSX 经 MinerU 解析生成 Markdown 并入库。
- 支持 MD 文件直接入库，TXT 经前端/大模型转换为 Markdown 后按 MD 落库。
- 实现上传记录、解析任务、解析分段三态状态机，支持 Stage2/Stage3/Stage4 定时任务兜底与用户决策重试。
- 实现文档版本管理（`doc_version`、`is_latest`、`version_remark`）。
- 实现模型功能适配配置，供 TXT 转 Markdown 按参数 ID `txt_to_markdown` 读取大模型。
- 前端新增「资料上传」页面与「Markdown 转换」页面。

**Non-Goals:**
- 本次不涉及 embedding 计算、文档分块、向量库写入、检索排序逻辑（表结构仅预留扩展）。

## Decisions

1. **状态机拆分**（参考需求文档 §3.1 / §3.2 / §3.3）
   - 上传记录状态与解析任务状态共享 `PENDING/LINK_FAILED/WAITING_UPLOAD/UPLOADING/PARSING/COMPLETED` 等公共状态，但完成/失败相关状态各自独立：上传记录使用 `USER_DECISION/CONVERTED/CONVERT_FAILED`，解析任务使用 `FAILED`。
   - 上传记录进入 `USER_DECISION` 等待用户选择重试或删除；解析任务进入 `FAILED` 表示存在失败情况。
   - 分段任务独立状态枚举 `WAITING_UPLOAD/UPLOAD_FAILED/PARSING/PARSED/PARSE_FAILED/RETRIED`，清晰表达分段生命周期。

2. **版本预占策略**（参考需求文档 §3.5 / §4.3.2 / §5.1）
   - 创建 `knowledge_upload_document_record` 时即对 `doc_title` 加锁并预占版本号，避免并发下版本冲突。
   - `knowledge_document` 创建时沿用上传记录的 `doc_version`，并按当前已落库最大版本动态设置 `is_latest`。

3. **失败重试机制**（参考需求文档 §3.6 / §6.2 / §6.3 / §6.4）
   - Stage2 消费者上传失败后，由 Stage2 定时任务兜底重试，按 `upload_expire_at` 判断链接是否过期，过期后将分段标记为 `PARSE_FAILED`。
   - 当 batch 下所有 detail 都已超时失败（无剩余非失败分段）时，解析任务状态更新为 `FAILED`，上传记录状态更新为 `USER_DECISION`。
   - 用户选择「重试」后，旧任务标记为 `COMPLETED`，旧失败分段标记为 `RETRIED`，新增任务从 `PENDING` 开始。

4. **Stage4 拖底策略**（参考需求文档 §6.5 / §6.6）
   - md 合并与入库异常时上传记录状态为 `CONVERT_FAILED`，由 Stage4 定时任务每 5 分钟扫描并重新发布 `document.md.pending`，不限制重试次数，用户可主动删除终止。

5. **TXT 转 Markdown 模式**（参考需求文档 §4.4 / §5.2）
   - 前端完成 TXT 编码识别与 UTF-8 转换，用户确认后调用 `POST /api/rag/document/txt/convert`。
   - 后端通过模型功能适配配置读取大模型配置，再使用 **LangChain 1.2.X** 调用大模型，将纯文本结构化后返回 Markdown；超过 512KB 直接拒绝。
   - 转换结果不入库，用户可选择下载 `.md` 或按上传 MD 文件落库。

6. **大模型调用框架选型**（由你明确要求；TXT 转 Markdown 参考需求文档 §5.2 / §10.4）
   - 统一使用 **LangChain 1.2.X** 提供大模型调用能力。
   - 现有 `knowledge-common` 中基于 agno 的 `AiUtil` 在本次变更中不再新增依赖，后续逐步删除；本次 TXT 转 Markdown 直接基于 LangChain 1.2.X 实现。

7. **Stage4 图片处理模型选型**（由你明确要求；图片处理流程参考需求文档 §6.5 步骤 6）
   - Stage4 合并 Markdown 时，对 ZIP 中提取的图片使用 **qwen3-vl-plus** 模型生成图片描述，并替换 Markdown 中的图片引用。
   - `qwen3-vl-plus` 模型初始化数据与 `deepseek-chat` 保持一致（字段结构相同，仅 `model_code`、`model_name`、API 相关配置不同）。

8. **模型功能适配下沉**（参考需求文档 §9.2 / §10.2.1）
   - `knowledge_ai_models` 的 DO/DAO/VO 从 `knowledge-admin` 下沉至 `knowledge-common`，`knowledge-admin` 仅保留业务层引用调整。

## Risks / Trade-offs

- **[Risk]** MinerU 上传链接 24 小时有效期与长时间大文件上传冲突 → **Mitigation**: 按任务创建时间 + 23 小时 50 分钟设置 `upload_expire_at`，超时后由 Stage2 兜底标记失败并进入用户决策。
- **[Risk]** 大模型 TXT 转 Markdown 处理大文本导致 Token 成本过高或效果下降 → **Mitigation**: 512KB 硬限制，超限提示用户拆分。
- **[Risk]** 多版本并发上传时 `is_latest` 短暂不一致 → **Mitigation**: 上传记录 `is_latest` 在创建时更新，文档 `is_latest` 在落库时更新；列表以各自表内最新版本为准，RAG 检索使用 `knowledge_document.is_latest='1'`。
- **[Risk]** 已生成 `knowledge_document` 的文档被删除可能影响下游分块/向量化 → **Mitigation**: 本期禁止删除已落库文档，仅允许删除尚未生成 `knowledge_document` 的记录。
- **[Risk]** 从 agno 切换到 LangChain 1.2.X 可能引入模型调用行为差异或依赖冲突 → **Mitigation**: 在 `knowledge-common` 中新建 LangChain 模型工厂，本次仅 TXT 转 Markdown 场景接入验证，其余场景按变更节奏逐步迁移，避免一次性全量替换。

## Migration Plan

1. 执行数据库 DDL 脚本，新建表结构。
2. 在 `knowledge-common` 中引入 LangChain 1.2.X 依赖，并新建大模型调用工厂/工具类。
3. 执行数据初始化脚本：`merio_language` 字典、`knowledge_ai_models` 与 `knowledge_ai_model_function_adapter` 初始记录。
4. 在 `knowledge-admin` 菜单/接口权限中注册 `knowledge-rag` 新接口权限编码。
5. 前端 `vite.config.js` 与 nginx 配置新增 `knowledge-rag` 代理。
6. 逐步部署 `knowledge-common`、`knowledge-admin`、`knowledge-rag`、`knowledge-web`。

## Open Questions

- 无
