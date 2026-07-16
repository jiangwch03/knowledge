# 文档主表去 Key 与文件子表改造方案

> 状态：实施中（OpenSpec change `document-file-subtable`）  
> 范围：网页爬取落库去合并 + `knowledge_document` 文件 Key 下沉 + 资料上传落库适配  
> 原则：状态机枚举值 / Topic / 上传解析流水线尽量不动；产品与 Agent 去「合并」歧义；合并实现代码保留可复用

---

## 1. 业务背景与目标

### 1.1 现状问题

当前网页爬取完成后，异步消费者会把**多页 Markdown 合并成一份**，再写入 `knowledge_document`（`doc_key` 指向合并后的 MinIO 对象）。

问题：

- 合并后的整包文档不利于按页检索、预览、选择性下载；
- `knowledge_document` 只有一个 `doc_key` 字段，天然假设「一文一文件」；
- 爬取与上传虽然共用文档主表，文件存放语义被绑死在主表列上，扩展成本高。

### 1.2 业务目标

1. **爬取不再做最终网页合并**：爬取任务完成后仍发原 Topic，改为把各成功页的已上传文件信息落到子表；
2. **文档主表只做元数据**：列表、版本、来源、任务关联仍以 `knowledge_document` 为分页基础；
3. **文件 Key 统一下沉到新表**：上传与爬取同一模型——上传 1 文档对应 1 文件行，爬取 1 文档对应 N 文件行；
4. **预览 / 下载按来源区分**：上传直接打开唯一文件；爬取需选页 / 多页 / 全量，多文件打包 zip；
5. **文案与工具语义去「合并」歧义**：Agent 工具名、HITL 提示、前端按钮/确认框等凡表达「把已成功页写入知识库」的，一律改为「入库」语义（见 §5.1）；
6. **最小扰动**：爬取任务状态机、消息 Topic、资料上传 Stage1～3 / MinerU 逻辑不动；合并**实现代码**保留以便日后迁回（产品侧不再出现「合并」表述）。

### 1.3 非目标

- 不改爬取执行、URL 记录、暂停/重试/HITL 等主流程（HITL 文案除外，见 §5.1）；
- 不改上传解析分段、MinerU、Stage4 兜底调度逻辑（仅改「写入 document」那一截）；
- 本期不做「把多页重新合并回一文」的产品入口（实现代码保留即可）。

---

## 2. 业务模型

### 2.1 文档与文件的关系

```
knowledge_document（业务文档 / 列表分页主体）
        │
        │  1 : N
        ▼
knowledge_document_file（建议表名，文件与 MinIO Key）
```

| 来源 `source_type` | 主表行数 | 子表行数 | 业务含义 |
|---|---|---|---|
| 手动上传 `0` | 1 | **1** | 一份资料 → 一份最终 Markdown（可带原始文件 Key） |
| 网页爬取 `1` | 1 | **N** | 一次爬取任务 → 一篇业务文档 → 每成功页一行文件 |

### 2.2 列表

- 资料上传文档列表、爬取文档列表：**仍按 `knowledge_document` 分页查询**；
- 不因子表行数膨胀列表；任务维度过滤继续用 `task_id` + `source_type`。

### 2.3 预览与下载

```
用户打开某条 knowledge_document
        │
        ▼
按 source_type 分支
├── 上传：子表仅 1 行 → 直接预览 / 下载该文件
└── 爬取：先展示子表页列表（标题 / URL / 文件名）
          ├── 预览：选择 1 页
          ├── 下载：选择 1 页 / 多页 / 全量
          └── 多页或全量 → 服务端打包 zip 下载
```

约定：

- **预览只支持单页**（多页预览无产品意义）；
- **下载支持单页、多选、全量**；多文件统一 zip。

---

## 3. 数据设计

### 3.1 `knowledge_document` 变更

删除与「具体文件」绑定的列及无用统计列（全部下沉到子表）：

| 删除字段 | 原含义 | 说明 |
|---|---|---|
| `doc_key` | 最终 Markdown MinIO 对象键 | 下沉到子表 |
| `original_doc_key` | 原始上传文件 MinIO 对象键 | 下沉到子表 |
| `source_url` | 网页来源 URL | 与 `doc_key` 一一对应，下沉到子表；任务入口 URL 仍在 `knowledge_web_crawler_task.target_url` |
| `doc_name` | 文件名 | 下沉到子表（与文件行绑定，业务语义更合适） |
| `doc_type` | 文档格式 | 下沉到子表 |
| `media_count` | 媒体文件数量 | **死字段**：从未被业务写入或读取，本期一并删除 |

主表保留：`doc_title`、版本、`source_type`、`task_id`、状态、审计字段等（文档级元数据，不绑定具体文件）。

> `knowledge_upload_document_parse_task` 上的 `doc_name` / `doc_type` / `original_doc_key` **保留**：上传解析流水线与上传任务列表仍用任务表字段；仅 `knowledge_document` 落库后的文件信息改走子表。

### 3.2 新表：`knowledge_document_file`（建议名）

承载「未合并 / 按文件粒度」的上传信息。

| 字段 | 类型（建议） | 说明 |
|---|---|---|
| `id` | bigint PK | 文件行主键 |
| `doc_id` | bigint | 关联 `knowledge_document.doc_id` |
| `task_id` | bigint | 冗余关联任务（上传任务 ID 或爬取任务 ID），便于按任务排查 |
| `doc_name` | varchar(255) | 文件名；上传从任务抄入；爬取可用 `{title}.md` 或由 URL 生成 |
| `doc_type` | varchar(50) | 文档格式；上传如 `PDF`/`MD`；爬取一般为 `MD` |
| `source_url` | text | 与本行 `doc_key` 对应的原始网页 URL；上传可空 |
| `original_doc_key` | varchar(500) | 原始文件 MinIO Key；爬取一般空，上传填原文件 |
| `doc_key` | varchar(500) | 最终 Markdown MinIO Key（爬取时与 `source_url` 同页对应） |
| `create_by` / `create_time` | | 审计 |
| `update_by` / `update_time` | | 审计 |
| `del_flag` | char(1) | 逻辑删除，`0` / `2` |

索引建议：

- `idx_doc_id`（`doc_id`）
- `idx_task_id`（`task_id`）
- 可选：`(doc_id, del_flag)`

子表一行 = 一个具体文件，字段语义对齐：

| 来源 | 典型写法 |
|---|---|
| 上传 | 1 行：`doc_name`/`doc_type`/`original_doc_key`/`doc_key` 有值，`source_url` 空 |
| 爬取 | N 行：每页 `source_url` + `doc_key`；`doc_type=MD`；`doc_name` 由 title/URL 生成；`original_doc_key` 空 |

> 资料上传任务列表仍查上传任务表（自带 `doc_name`/`doc_type`）。若知识库文档列表需要按格式筛选，改为关联子表（上传 1:1 可 join 唯一文件行）。

### 3.3 与现有爬取 URL 表的关系

```
knowledge_web_crawler_task
        ├── knowledge_web_crawler_task_url_record   ← 执行态：成败、单页 doc_key（爬取过程已有）
        └── knowledge_document                     ← 落库态：业务文档
                    └── knowledge_document_file    ← 落库态：从成功 url_record 抄入的文件行
```

- `url_record` 继续服务爬取执行、重试、删页清 MinIO；
- `document_file` 服务知识库文档的预览 / 下载 / 后续检索；
- 落库时从「成功且含 `doc_key` 的 url_record」拷贝到子表，不在落库阶段重新上传（单页 MD 在爬取后处理阶段已在 MinIO）。

### 3.4 ER（逻辑）

```
┌─────────────────────────────┐
│   knowledge_document        │
│   (元数据主表，无文件 Key)    │
└──────────────┬──────────────┘
               │ 1
               │
               │ N
┌──────────────▼──────────────┐
│ knowledge_document_file     │
│ doc_name / doc_type         │
│ source_url                  │
│ original_doc_key / doc_key  │
└─────────────────────────────┘
```

---

## 4. 流程改造

### 4.1 网页爬取落库（核心）

**不变：**

- 爬取全部完成后任务 → `COMPLETED`；
- 投递现有 Topic：`crawl.document.pending`；
- 消费者标记 `CONVERTING` → 落库成功 `CONVERTED` / 失败 `CONVERT_FAILED`；
- 状态枚举值与 Topic 名不改。

**变更：**

```
crawl.document.pending
        │
        ▼
  CONVERTING
        │
        ├─ 创建 1 条 knowledge_document（无文件字段；可写 doc_title）
        ├─ 按成功 url_record 写入 N 条 knowledge_document_file
        │     doc_key ← url_record.doc_key
        │     source_url ← url_record.url
        │     doc_name ← `{title}.md` 或由 URL 生成
        │     doc_type ← MD
        │     original_doc_key ← NULL
        └─ 不再调用多页 Markdown 合并上传
        │
        ▼
     CONVERTED
```

**代码保留（停用调用）：**

- `CrawlerDocumentService._merge_pages_to_temp`
- `_upload_merged_to_minio`
- `_create_merged_document`  
  以及相关合并路径，便于日后「合并迁回」复用。

**幂等：**

- 仍可「任务下已存在 `source_type=爬取` 的 document 则跳过整批」（保持一任务一文）；
- 或落库事务内先写主表再写子表，失败走现有 `CONVERT_FAILED` + 定时重投 Topic。

**单页与多页：**

- 统一走「1 主表 + N 子表」（N≥1），不再区分合并 / 不合并两条写主表 Key 的路径。

### 4.2 资料上传落库（仅适配）

**不动：** Stage1～3、MinerU、上传任务状态、Topic、任务表 `original_doc_key`。

**只改：** 写入 / 更新 `knowledge_document` 的位置（如 MD 直传创建文档、Stage4 合并 MD 后创建/更新文档）：

```
原：document.doc_key = 最终 MD；document.original_doc_key = 原文件
现：写 document（无文件字段；仍写 doc_title / 版本等）
    + 写 / 更新 document_file 1 行
         doc_name / doc_type ← 上传任务
         doc_key = 最终 MD
         original_doc_key = 任务表上的原文件 Key
         source_url 空
```

### 4.3 预览 / 下载

| 场景 | 行为 |
|---|---|
| 上传预览 | 查 `doc_id` 下唯一未删除文件行 → 下 `doc_key` → 内联 Markdown |
| 上传下载 | 同上，附件名用子表 `doc_name` |
| 爬取预览 | 必须指定 `file_id`（单页） |
| 爬取下载单页 | 指定一个 `file_id`，文件名用该行 `doc_name` |
| 爬取下载多页 / 全量 | `file_ids` 或 `all=1` → 多对象打包 zip（条目名用各行 `doc_name`） |

上传若误传 `file_id`：校验属于该 `doc_id` 即可；未传则取唯一行。  
爬取预览/下载未传选择且非全量：返回业务错误，提示先选页（或前端先调文件列表）。

---

## 5. 接口与产品文案改造

### 5.1 Agent / 前端：「合并」→「入库」（本期必做）

功能语义不变：放弃失败 URL，将已成功爬取页面投入文档落库队列（Topic 仍为 `crawl.document.pending`）。产品与 Agent 表述必须与「不再合并多页」一致，避免歧义。

| 位置 | 现状（示例） | 改造后（建议） |
|---|---|---|
| Agent 工具 | `merge_crawl_results` / 「合并已爬内容」 | `persist_crawl_results`（或保留函数别名兼容）/ 「入库已爬内容」 |
| Supervisor HITL | 「确认提交合并…投入文档合并队列」 | 「确认提交入库…投入文档落库队列」 |
| 前端按钮 | 「合并已爬内容」 | 「入库已爬内容」 |
| 确认框 | 「合并为知识库文档」 | 「将已成功页面写入知识库文档」 |
| API 路径/方法名（若对外暴露 merge） | `merge` | 改为 `persist` / `convert` 等同义，或路径保留但文档与返回文案改「入库」 |
| 状态展示文案（可选加强） | `CONVERTING` 展示「合并中」 | 展示「落库中」/「入库中」（枚举值仍用 `CONVERTING`，只改 label） |

说明：

- **枚举值 / Topic 名可不改**（`CONVERTING`、`crawl.document.pending`），改的是对用户与 LLM 可见的名称与文案；
- 工具若重命名，须同步注册表、HITL `case`、前端调用与测试；可短时保留旧 tool name 为 deprecated alias，避免会话内旧 checkpoint 找不到工具（若无此顾虑可直接改名）。

### 5.2 文档预览 / 下载接口（建议）

现有：

- `GET /document/{doc_id}/preview`
- `GET /document/{doc_id}/download`

扩展建议：

| 接口 | 说明 |
|---|---|
| `GET /document/{doc_id}/files` | 子表文件列表（爬取选页用；上传也可返回 1 条） |
| `GET /document/{doc_id}/preview?file_id=` | 上传可省略 `file_id`；爬取必填 |
| `GET /document/{doc_id}/download?file_id=` | 单文件 |
| `GET /document/{doc_id}/download?file_ids=1,2,3` | 多文件 → zip |
| `GET /document/{doc_id}/download?all=1` | 该文档下全部未删除文件 → zip |

实现注意：

- zip 在临时目录组装，响应后清理（与现有 `FileResponse` + 临时文件清理一致）；
- 权限沿用现有 `rag:document:preview` / `rag:document:download`（或按模块拆分，非必须）；
- 爬取文档列表页仍走现有 crawler document list（按主表）；选页 UI 在预览/下载动作时展开。

---

## 6. 技术落地清单

### 6.1 数据库

1. 新建 `knowledge_document_file`（字段见 §3.2）；  
2. `knowledge_document` 删除 `doc_key`、`original_doc_key`、`source_url`、`doc_name`、`doc_type`、`media_count`；  
3. 数据迁移（若有存量）：
   - 上传 / 已合并爬取文档：主表旧文件字段 → 插入 1 条子表；
   - 历史「合并包」作为 1 个文件行保留（`source_url` 填原主表值或任务 `target_url`）；新任务按成功页逐行写入。

### 6.2 后端模块

| 模块 | 改动要点 |
|---|---|
| DO / DAO | 新表实体与 CRUD；`KnowledgeDocument` 去掉 Key 字段 |
| `CrawlerDocumentService` | 停用合并调用；写主表 + 批量写子表；合并方法保留 |
| `crawl_document_consumer` | 逻辑可几乎不动，仍调 `persist_documents` |
| `DocumentUploadParseService` | 仅 `_create_knowledge_document` / Stage4 写文档处适配子表 |
| `DocumentService` | 预览下载改读子表；增加按 `source_type` 分支与 zip |
| Controller / VO | 文件列表、preview/download 查询参数 |
| 测试 / seed | 覆盖上传 1 文件、爬取 N 文件、预览下载、迁移脚本 |

### 6.3 前端 / Agent 文案（与读侧配套，本期必做）

| 模块 | 改动要点 |
|---|---|
| 资料文档预览/下载 | 上传路径可保持「一键」；底层兼容无 `file_id` |
| 爬取文档预览/下载 | 文件列表展示 `doc_name` / `source_url` / `doc_type`；支持多选 / 全量 zip |
| 列表页 | 主表分页；需展示文件名/格式时关联子表（上传 1:1；爬取可摘要「N 个文件」） |
| 上传任务列表 | **不动**（仍用上传任务表自身的 `doc_name`/`doc_type`） |
| 爬取任务操作 | 「合并已爬内容」→「入库已爬内容」；确认框/成功提示同步 |
| Agent 工具与 HITL | 工具名与描述去「合并」；HITL 确认文案改为入库（见 §5.1） |
| 状态 label（建议同期） | `CONVERTING` 展示由「合并中」改为「落库中」/「入库中」 |

### 6.4 文档与 Spec

- 更新 `openspec/specs/web-crawler-agent` 中「异步合并 Markdown」要求 → 「逐页文件落子表」；
- 更新 `docs/rag/网页爬取Agent/06-数据库设计.md`、文档上传相关说明中主表字段描述。

---

## 7. 风险与对策

| 风险 | 对策 |
|---|---|
| 存量数据依赖主表 `doc_key` | 升级脚本先迁子表再删列；预览下载切读子表 |
| 爬取页数很大时全量 zip 耗时/内存 | 流式写 zip 到临时文件；必要时限制单次文件数或异步下载（可二期） |
| 主表删 `source_url` 后入口 URL 去哪查 | 用爬取任务表 `target_url`；列表「来源 URL」列改展示子表（多页可摘要/首条/「N 页」） |
| 合并代码长期死代码 | 方法保留并注释「迁回用」；不在默认路径调用 |
| 上传 Stage4 与直传两处写文档 | 抽一小段「写主表 + 写文件行」复用，避免只改一处 |

---

## 8. 实施分期建议

**P0（本方案闭环）**

1. 建表 + 主表删列 + 迁移脚本  
2. 爬取落库去合并（写主表 + N 子表）  
3. 上传落库适配（写主表 + 1 子表）  
4. 预览/下载按 `source_type` 分支 + 爬取选页/zip  
5. Agent 工具名/描述、HITL、前端按钮与确认框：「合并」→「入库」；状态展示 label 同步  
6. 单测与关键路径冒烟  

**P1（体验）**

- 前端爬取选页 / 全量下载交互打磨  
- 全量 zip 限流或异步  

**P2（可选）**

- 合并迁回能力（复用保留代码 + 子表为输入）  

---

## 9. 验收要点

1. 多页爬取完成 → `CONVERTED`，主表 1 条，子表 = 成功页数，MinIO **无**新的 `merged/merged_result.md`；  
2. 单页爬取同样 1 主表 + 1 子表；  
3. 上传 MD 直传 / Stage4 完成后主表无 Key，子表 1 行 Key 正确；  
4. 文档列表仍按主表分页，上传与爬取列表正常；  
5. 上传预览/下载一键可用；  
6. 爬取须选页才能预览；多选/全量下载得到 zip，内容为所选页 Markdown；  
7. 合并相关私有方法仍存在于代码库且默认路径不调用；  
8. Topic 名与爬取任务状态枚举值未变更；  
9. 用户与 Agent 可见文案不再出现「合并已爬内容」等表述，统一为「入库」语义。

---

## 10. 决议摘要

| 项 | 决议 |
|---|---|
| 爬取最终合并 | 不做；实现代码保留 |
| Topic / 状态枚举值 | 不动 |
| 「合并」产品/Agent 文案 | **本期必改**为「入库」 |
| 文档列表 | 继续按 `knowledge_document` 分页 |
| 文件级字段 | 主表删除 `doc_key`、`original_doc_key`、`source_url`、`doc_name`、`doc_type`；全部下沉 `knowledge_document_file` |
| `media_count` | 主表删除（无业务使用） |
| 上传改造范围 | 仅文档落库适配新表 |
| 预览 | 上传直接；爬取单页必选 |
| 下载 | 上传直接；爬取单页/多页/全量，多文件 zip |

---

## 修订记录

| 日期 | 说明 |
|---|---|
| 2026-07-16 | 初稿：探索对齐后的业务到落地方案 |
| 2026-07-16 | Agent/前端「合并」文案改为本期必做「入库」 |
| 2026-07-16 | 主表删除无用字段 `media_count` |
| 2026-07-16 | `source_url` 随 `doc_key` 迁入子表（页级一一对应） |
| 2026-07-16 | `doc_name`/`doc_type` 亦下沉子表（与文件行绑定，语义统一） |
