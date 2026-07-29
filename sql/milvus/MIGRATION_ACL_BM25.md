# Milvus ACL + BM25 + parent_chunk_id 说明

> 配套 DDL：`sql/milvus/manage_document_vector.py`（仅创建/重建 collection）  
> 写路径：`knowledge-content` upsert 已写入 `dept_id` / `user_id` / `parent_chunk_id`；BM25 sparse 由 text Function 自动生成

## 变更摘要

1. 标量字段：`dept_id`、`user_id`（INVERTED，data_scope）
2. `parent_chunk_id`（INVERTED；对齐 `knowledge_document_segment.parent_chunk_id`，无父为空串）
3. `text` 启用 analyzer；`sparse` + BM25 Function `text_bm25`
4. BM25 / analyzer **必须在建 collection 时定义**，无法对存量 collection 原地追加

## 建表

```bash
uv run python sql/milvus/manage_document_vector.py
```

注意：会 **drop 后重建**，数据清空；存量需重新向量化或自行从 MySQL 回灌。

## 验收清单

- [x] `describe_collection` 含 `parent_chunk_id` / `dept_id` / `user_id` / `sparse`
- [x] 本环境已回灌 VECTOR_STORED（含 `parent_chunk_id`）
- [ ] `POST /retrieval/search` 冒烟；子片命中可父片回填
- [ ] 越权文档不出现在检索 hits
