## MODIFIED Requirements

### Requirement: 文档预览（参考需求文档 §5.7）
系统 SHALL 提供文档预览接口：从来源为手动上传的 `knowledge_document` 关联的 `knowledge_document_file` 读取最终 Markdown 的 MinIO 对象并返回预览。上传场景可省略文件行 ID（取该文档下唯一未删除文件行）。

#### Scenario: 预览已转换文档
- **WHEN** 用户点击已 `CONVERTED` 的上传文档预览按钮
- **THEN** 系统从该文档唯一文件行的 `doc_key` 对应 MinIO 对象读取 Markdown 并返回预览

### Requirement: 文档下载（参考需求文档 §5.8）
系统 SHALL 提供文档下载接口，以流形式下载 Markdown 文件；文件内容与下载文件名取自 `knowledge_document_file` 的 `doc_key` 与 `doc_name`。

#### Scenario: 下载已转换文档
- **WHEN** 用户点击已 `CONVERTED` 的上传文档下载按钮
- **THEN** 系统从该文档唯一文件行下载 Markdown，并以 `application/octet-stream` 返回，文件名使用子表 `doc_name`

### Requirement: Stage4 消费者合并 Markdown 并入库（参考需求文档 §6.5；图片模型由你明确要求为 qwen3-vl-plus）
系统 SHALL 消费 `document.md.pending` 消息，下载 ZIP、合并 Markdown、使用 `qwen3-vl-plus` 模型生成图片描述并替换 Markdown 图片引用、上传最终 Markdown 至 MinIO，创建或更新 `knowledge_document`，并写入/更新对应的 1 条 `knowledge_document_file`（`doc_key` 为最终 Markdown，`original_doc_key` 来自上传任务，`doc_name`/`doc_type` 来自上传任务）。Stage1～3 与 MinerU 解析逻辑不变。

#### Scenario: md 合并与入库成功
- **WHEN** Stage4 消费者成功处理 `document.md.pending`
- **THEN** 系统完成 ZIP 合并与图片描述替换，上传最终 Markdown 至 MinIO，创建或更新 `knowledge_document`（主表不含文件 Key 字段），写入或更新 1 条 `knowledge_document_file`，上传记录状态更新为 `CONVERTED`

#### Scenario: md 合并异常进入 Stage4 兜底
- **WHEN** md 合并或入库过程出现异常
- **THEN** 上传记录进入可被 Stage4 定时任务兜底重试的失败状态

## ADDED Requirements

### Requirement: MD 直传落库写入文件子表
系统 SHALL 在无需 MinerU 解析的 MD 直传场景创建 `knowledge_document` 时，同时写入 1 条 `knowledge_document_file`，将最终 Markdown 对象键与原始文件键（若与最终相同或来自任务）保存在子表，而非主表。

#### Scenario: MD 直传生成文档与文件行
- **WHEN** 用户上传 MD 且系统直接落库
- **THEN** 系统创建 `knowledge_document` 与 1 条 `knowledge_document_file`，上传记录状态为 `CONVERTED`
