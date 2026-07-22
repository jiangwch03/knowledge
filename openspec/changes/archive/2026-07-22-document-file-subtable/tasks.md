## 1. 数据库与模型

- [x] 1.1 编写 SQL：创建 `knowledge_document_file`（字段含 doc_id、task_id、doc_name、doc_type、source_url、original_doc_key、doc_key、审计与索引）
- [x] 1.2 编写迁移：将现有 `knowledge_document` 文件字段迁入子表（每文档至少 1 行）
- [x] 1.3 编写 SQL：删除主表 `doc_key`、`original_doc_key`、`source_url`、`doc_name`、`doc_type`、`media_count`
- [x] 1.4 新增 `KnowledgeDocumentFile` DO / DAO（增删查、按 doc_id 列表、软删）
- [x] 1.5 更新 `KnowledgeDocument` DO：移除已删列对应属性

## 2. 爬取落库

- [x] 2.1 改造 `CrawlerDocumentService.persist_documents`：统一写 1 主表 + N 子表；停用合并调用路径
- [x] 2.2 保留 `_merge_pages_to_temp` / `_upload_merged_to_minio` / `_create_merged_document` 并标注迁回用途
- [x] 2.3 确认 `crawl_document_consumer` 仍走原 Topic，幂等与 CONVERTING/CONVERTED/CONVERT_FAILED 行为符合设计
- [x] 2.4 更新爬取相关单测与 `seed_crawl_test_data`（多页无 merged 对象、子表行数=成功页数）

## 3. 上传落库适配

- [x] 3.1 抽取「写/更新 knowledge_document + 1 条 document_file」供复用
- [x] 3.2 改造 MD 直传创建文档路径，写入子表
- [x] 3.3 改造 Stage4 创建/更新文档路径，写入/更新子表（Stage1～3 / MinerU 不动）
- [x] 3.4 更新 `test_document_upload_parse_service` / stage 状态相关测试中的文档落库断言

## 4. 预览 / 下载 / 文件列表 API

- [x] 4.1 `DocumentService` 改读子表；按 `source_type` 分支（上传可省略 file_id；爬取预览必选）
- [x] 4.2 实现多文件/全量 zip 下载（条目名用 `doc_name`，临时文件清理）
- [x] 4.3 Controller：`GET /document/{doc_id}/files`；扩展 preview/download 查询参数
- [x] 4.4 补充预览/下载/文件列表 VO 与权限依赖

## 5. Agent / 前端「入库」文案

- [x] 5.1 重命名或包装 `merge_crawl_results` → `persist_crawl_results`（按需保留旧名 alias）；更新工具描述与注册
- [x] 5.2 更新 Supervisor HITL 确认文案为「入库」
- [x] 5.3 前端「合并已爬内容」按钮、确认框、成功/失败提示改为「入库」
- [x] 5.4 `CONVERTING` 展示 label 改为「落库中」或「入库中」（枚举值不变）
- [x] 5.5 更新相关 Agent/前端测试与 API 文案

## 6. 前端读侧（爬选取页）

- [x] 6.1 爬取文档预览：先拉 files 列表再选单页预览
- [x] 6.2 爬取文档下载：支持单页 / 多选 / 全量 zip
- [x] 6.3 文档列表：主表分页；需展示文件名/格式时关联子表或摘要（上传任务列表不动）

## 7. 文档与验收

- [x] 7.1 同步更新 `docs/rag/网页爬取Agent/06-数据库设计.md` 与方案文档状态为「实施中/已立项」
- [x] 7.2 冒烟：多页爬取 CONVERTED、无 merged 对象、子表行数正确；上传落库子表 1 行；上传一键预览下载；爬选取页预览与 zip
- [x] 7.3 确认合并私有方法仍在库中且默认路径不调用；Topic 与状态枚举值未改
