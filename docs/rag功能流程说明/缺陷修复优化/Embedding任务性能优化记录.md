# Embedding 任务性能优化

## 背景

大文档 Embedding（约 10 万段）跑起来后，管理端任务列表等接口明显变慢；当时主要卡在「向量写 MySQL」阶段，与 Milvus 索引无关。

## 原因

1. **分段表索引缺失**：`knowledge_document_segment` 线上几乎只剩主键，按 `task_id` 拉批 / COUNT 全表扫描。
2. **同步 Embedding 堵事件循环**：`embeddings.embed_documents()` 是阻塞 HTTP，在 async 流水线里直接调用，同进程其它接口一起卡住。
3. **批处理串行**：阶段一 Embedding / 阶段二刷 Milvus 按批顺序跑，墙钟时间过长。

## 修复

1. **补齐 MySQL 索引**（写入 `sql/upgrade_knowledge_content.sql` 等，ORM `__table_args__` 同步声明），关键复合索引：`idx_task_embed_queue (task_id, skip_embedding, status, del_flag, file_id, chunk_order)`。
2. **阻塞调用丢线程池**：

```python
vectors = await asyncio.to_thread(embeddings.embed_documents, texts)
```

3. **单任务内工人池并发**：id 入队 + 固定工人领批；实现见 `embedding_concurrent_service.py`。配置：

| 变量 | 默认 | 说明 |
|------|------|------|
| `EMBEDDING_EMBED_CONCURRENCY` | `4` | 同时在飞批次数（过大易限流） |
| `EMBEDDING_EMBED_BATCH_SIZE` | `100` | 每批条数 |

与全局 `SEMAPHORE_EMBEDDING_PIPELINE_SIZE`（同时跑几个任务）正交。改配置后需重启 knowledge-content。
