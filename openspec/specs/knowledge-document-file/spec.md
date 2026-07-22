## Purpose

规范 `knowledge_document_file` 文件子表：与文档主表解耦的文件级字段、按来源预览/下载，以及文件列表接口。

## Requirements

### Requirement: 文档文件子表
系统 SHALL 使用 `knowledge_document_file` 存储与单个文件绑定的字段：`doc_name`、`doc_type`、`source_url`、`original_doc_key`、`doc_key`，并通过 `doc_id` 关联 `knowledge_document`，通过 `task_id` 冗余关联上传或爬取任务。

#### Scenario: 上传文档对应一行文件
- **WHEN** 资料上传落库生成 `knowledge_document`
- **THEN** 系统写入恰好 1 条未删除的 `knowledge_document_file`，包含最终 Markdown 的 `doc_key` 与任务上的 `original_doc_key`（若有），`source_url` 为空

#### Scenario: 爬取文档对应多行文件
- **WHEN** 网页爬取任务落库且存在 N 个成功且含 `doc_key` 的 URL 记录
- **THEN** 系统写入 N 条 `knowledge_document_file`，每行 `source_url` 与 `doc_key` 对应同一成功页，`doc_type` 为 MD

### Requirement: 文档主表不含文件级字段
系统 SHALL NOT 在 `knowledge_document` 上持久化 `doc_key`、`original_doc_key`、`source_url`、`doc_name`、`doc_type`、`media_count`。

#### Scenario: 主表仅元数据
- **WHEN** 查询 `knowledge_document` 列表分页
- **THEN** 系统仍以主表为分页主体，文件内容通过子表关联获取

### Requirement: 按来源预览文档文件
系统 SHALL 按 `source_type` 提供预览：手动上传可省略 `file_id` 并预览唯一文件行；网页爬取 MUST 指定单个 `file_id` 预览对应 Markdown。

#### Scenario: 上传一键预览
- **WHEN** 用户预览来源为手动上传且已落库的文档且未传 `file_id`
- **THEN** 系统使用该 `doc_id` 下唯一未删除文件行的 `doc_key` 返回 Markdown 预览

#### Scenario: 爬取必须选页预览
- **WHEN** 用户预览来源为网页爬取的文档且未传 `file_id`
- **THEN** 系统拒绝预览并提示需选择页面（或先拉取文件列表）

#### Scenario: 爬取指定页预览
- **WHEN** 用户传入属于该 `doc_id` 的 `file_id` 请求预览
- **THEN** 系统返回该文件行 Markdown 内容

### Requirement: 按来源下载文档文件
系统 SHALL 支持单文件下载；对网页爬取还 SHALL 支持多 `file_id` 或全量下载，并将多个 Markdown 打包为 zip；附件名使用子表 `doc_name`。

#### Scenario: 上传一键下载
- **WHEN** 用户下载来源为手动上传的文档且未传 `file_id`
- **THEN** 系统以下表唯一文件行的内容与 `doc_name` 返回单文件下载

#### Scenario: 爬取多页 zip 下载
- **WHEN** 用户对爬取文档指定多个 `file_id` 或 `all=1` 下载
- **THEN** 系统返回 zip，内含所选（或全部）文件行对应的 Markdown，条目名取自各行 `doc_name`

### Requirement: 文档文件列表接口
系统 SHALL 提供按 `doc_id` 查询未删除文件行列表的接口，供爬选取页与上传核对使用。

#### Scenario: 列出文档下文件
- **WHEN** 用户请求某 `doc_id` 的文件列表
- **THEN** 系统返回该文档下未删除的 `knowledge_document_file` 记录（含 `id`、`doc_name`、`doc_type`、`source_url` 等）
