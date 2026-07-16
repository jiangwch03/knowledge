## Context

爬取落库当前在 `CrawlerDocumentService`：单页写主表 `doc_key`，多页合并 MD 后再写一条主表。资料上传在 MD 直传 / Stage4 同样把 `doc_key`、`original_doc_key` 写在 `knowledge_document`。预览下载 `DocumentService` 直接读主表 Key。

业务对齐文档：`docs/rag/文档主表去Key与文件子表改造方案.md`。本 design 固化技术决策，实施以本 change 的 specs / tasks 为准。

约束：状态枚举值与 `crawl.document.pending` Topic 不变；上传 Stage1～3 / MinerU 不变；多页合并实现代码保留可迁回。

## Goals / Non-Goals

**Goals:**

- 主表仅文档元数据；文件级字段统一在 `knowledge_document_file`
- 爬取：1 主表 + N 子表，不合并；上传落库：1 主表 + 1 子表
- 预览/下载按 `source_type` 分支；爬取支持选页与 zip
- Agent / 前端「合并」文案改为「入库」

**Non-Goals:**

- 不改爬取执行、url_record、暂停/重试主流程（除入库相关 HITL 文案）
- 不做「多页再合并回一文」产品入口
- 不改上传任务表结构与解析流水线主体
- 不做全量 zip 异步/限流（可 P1）

## Decisions

### 1. 子表承载全部文件字段

- **选择**：`knowledge_document_file` 含 `doc_name`、`doc_type`、`source_url`、`original_doc_key`、`doc_key` + `doc_id`/`task_id` + 审计
- **理由**：与「一行一个文件」语义一致；主表删对应列（含无用 `media_count`）
- **备选**：`doc_name`/`doc_type` 留主表 → 已否决（文件语义应在子表）

### 2. 爬取落库停用合并，代码保留

- **选择**：`persist_documents` 统一写 1 主表 + N 子表（从成功 `url_record` 抄 Key）；`_merge_*` 保留不调用
- **理由**：最小改 Topic/状态机；合并可迁回
- **幂等**：任务下已有爬取 `knowledge_document` 则整批跳过（仍一任务一文）

### 3. 上传只改编库写路径

- **选择**：抽「写主表 + 写/更新 1 文件行」供 MD 直传与 Stage4 复用
- **理由**：解析流水线不动；任务表仍持有流水线用的 `original_doc_key`/`doc_name`/`doc_type`

### 4. 预览/下载 API

- **选择**：`GET .../files`；preview/download 支持 `file_id` / `file_ids` / `all=1`；上传可省略 `file_id`（取唯一行）；爬取预览必选单页；多文件 zip
- **理由**：列表仍按主表分页；读侧按来源分支

### 5. 「合并」→「入库」产品语义

- **选择**：工具建议 `persist_crawl_results`（可留旧名 alias）；HITL/按钮/确认框改「入库」；`CONVERTING` label 改为「落库中/入库中」，枚举值不变
- **理由**：避免与「不再合并多页」冲突

### 6. 与 url_record 分工

- **选择**：url_record 继续执行态；落库时拷贝到 `document_file`，不在落库阶段重新上传 MinIO
- **理由**：执行与知识库读模型解耦

## Risks / Trade-offs

- [存量依赖主表 Key] → 迁移脚本先插子表再删列；预览下载切读子表
- [大任务全量 zip] → 流式写临时 zip；P1 再限流/异步
- [主表无 source_url] → 任务入口用 `target_url`；列表文件信息 join 子表或摘要
- [合并死代码] → 注释标明迁回用途
- [文档列表展示 doc_name] → 上传 1:1 join；爬取展示「N 个文件」或首条

## Migration Plan

1. 建 `knowledge_document_file`
2. 将现有主表文件字段迁入子表（每文档 1 行；历史合并包保留为单文件行）
3. 应用读路径切子表后，删主表列
4. 部署爬取/上传写路径与文案改造
5. **回滚**：保留迁移备份或双写窗口；极端情况回滚应用版本并暂不删列（若已删列需反向脚本）

## Open Questions

- 无（业务决议已在方案文档 §10 固化；实施中工具是否保留 `merge_crawl_results` 别名按 checkpoint 兼容需要决定）
