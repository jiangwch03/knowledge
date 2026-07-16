## MODIFIED Requirements

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