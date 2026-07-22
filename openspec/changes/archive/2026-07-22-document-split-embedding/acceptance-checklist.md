# Embedding 验收清单（document-split-embedding）

> 部署前先执行：
> 1. `sql/upgrade_document_embedding_adapter.sql`
> 2. `sql/upgrade_document_embedding.sql`（或已含 A.7/A.8 的 `upgrade_knowledge_content.sql`）
> 3. 配置 `MILVUS_URI` / `MILVUS_TOKEN` / `MILVUS_COLLECTION`（可选）

## 6.1 Preview 不落库；提交成功 → VECTOR_STORED + canary

- [ ] 打开 Embedding 配置页，预览后查库：`knowledge_document_segment` / Milvus 无新增
- [ ] 提交任务 → 任务 `COMPLETED`；文档 `VECTOR_STORED`
- [ ] 本批 segment / Milvus `release_tag=canary`
- [ ] `skip_embedding=1` 父片无 Milvus 写入

## 6.2 新 canary 不删 prod；旧 canary 可替换

- [ ] 手工将一批 segment+向量标为 `prod` 后，再跑新 Embedding
- [ ] 新任务完成后 prod 仍在；新批为 canary
- [ ] 再跑一次：旧 canary 被软删/清向量，最新 canary 保留

## 6.3 手工验收（需求 §十）

- [ ] 上传/爬取列表可打开配置页，五策略可用
- [ ] 预览不落库、不 embed；爬取可切换页预览
- [ ] 维度只读来自 `document_embedding` 适配
- [ ] 进行中不可重复提交；FAILED 可重试
- [ ] 「Embedding 任务」菜单可用；release_tag 由 segment 聚合展示
- [ ] 任务轮询可见 PENDING→CHUNKING→EMBEDDING→COMPLETED
