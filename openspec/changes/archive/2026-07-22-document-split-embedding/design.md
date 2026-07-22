## Context

定稿见 `docs/rag/文档切分与向量化/`。同 `doc_id` 用 **`release_tag`（canary / prod / pending_delete）** 区分灰度与发布；**权威仅在 `knowledge_document_segment` ↔ Milvus**，文档表/任务表不存发布态。

## Goals / Non-Goals

**Goals:** 五策略切分+预览；异步 Embedding；成功写入 `release_tag=canary`；不碰已有 `prod`；schema 预留发布切换与监控。

**Non-Goals:** 发布切换 UI、RAGAS 页、监控看板、检索 API、自由填维度、**Embedding 模型切换/多 Profile**。

## Decisions

1. 自研切分 Factory。  
2. LangChain embed + pymilvus。  
3. 维度在业务适配 `document_embedding` 配置；任务页只读，禁止客户端自由填维。  
4. 人工提交任务。  
5. **release_tag 路由**：成功→canary；可顶替旧 canary；不碰 prod；发布时 canary→prod、旧 prod→pending_delete、异步清理。  
6. 检索：`release_tag=prod`（灰度可读 canary）。  
7. 失败重试新建任务。  

## Risks / Trade-offs

- 误伤 prod → 清理只针对 pending_delete/旧 canary  
- canary 堆积 → 同 doc 只留最新 canary  

## Open Questions

无。
