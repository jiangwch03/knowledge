## Why

网页爬取多页合并成单一 Markdown 后写入 `knowledge_document`，既不利于按页预览/选择性下载，也把「一文一文件」假设绑死在主表 `doc_key` 上。需要把文件级信息下沉到子表，爬取改为逐页入库，并与资料上传落库模型统一。

详细业务对齐见：`docs/rag/文档主表去Key与文件子表改造方案.md`。

## What Changes

- 新建 `knowledge_document_file`：承载 `doc_key` / `original_doc_key` / `source_url` / `doc_name` / `doc_type` 等文件级字段
- **BREAKING**：`knowledge_document` 删除 `doc_key`、`original_doc_key`、`source_url`、`doc_name`、`doc_type`、`media_count`；存量数据迁移到子表后再删列
- 爬取落库：不再合并多页 Markdown；`COMPLETED` → 原 Topic → 1 条主表 + N 条子表；合并实现代码保留但不默认调用
- 资料上传：仅适配「写入/更新 knowledge_document」为写主表 + 1 条子表；Stage1～3 / MinerU / 任务表逻辑不动
- 预览/下载按 `source_type` 分支：上传一键；爬取选页 / 多选 / 全量 zip
- 产品与 Agent 文案：「合并已爬内容」→「入库已爬内容」（工具名、HITL、前端按钮；状态枚举值 / Topic 名不变）

## Capabilities

### New Capabilities

- `knowledge-document-file`: 文档文件子表、按来源的预览/下载（含爬取选页与 zip）、主表去文件字段后的读写契约

### Modified Capabilities

- `web-crawler-agent`: 文档落库由「异步合并 Markdown」改为「逐页写入文件子表」；任务工具「合并」语义改为「入库」
- `rag-document-upload`: 创建/更新 `knowledge_document` 时文件 Key 写入子表；预览/下载改读子表（上传解析流水线其余部分不变）

## Impact

- **DB**：新表 + 主表删列 + 迁移脚本
- **Backend**：`CrawlerDocumentService`、`DocumentUploadParseService` 落库、`DocumentService` 预览下载、document/crawler controller 与 VO、Agent `merge_crawl_results` 重命名/文案、相关测试与 seed
- **Frontend**：爬取入库按钮与确认文案；爬取文档预览/下载选页与 zip；文档列表展示文件名/格式时关联子表
- **不变**：爬取状态枚举值、`crawl.document.pending` Topic、上传 Stage1～3 / MinerU、上传任务表字段
- **参考文档**：`docs/rag/文档主表去Key与文件子表改造方案.md`
