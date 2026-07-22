## Why

资料上传与网页爬取已将文档统一转为 Markdown（`CONVERTED`），但缺少可配置的切分与向量化入库能力，无法支撑后续检索与 RAGAS 测评。本期补齐五策略切分 + LangChain Embedding + Milvus 存储，并以配置预览与异步任务完成产品闭环。

## What Changes

- 新增五策略文档切分（TITLE / LENGTH / SEPARATOR / REGEX / SMART）与同步效果预览
- 新增 Embedding 异步任务：成功写入 **`release_tag=canary`**，不自动改写已有 **prod**
- 资料上传、网页爬取文档列表增加 Embedding 入口与配置页
- 新建「Embedding 任务」菜单
- Embedding 模型适配；维度只读
- **扩展就绪**：同 doc 下 canary/prod/pending_delete；发布时旧 prod→pending_delete 异步清理；检索按标签过滤
- **本期不做**：发布切换 UI、RAGAS 页、监控看板、检索 API、**Embedding 模型切换**

## Capabilities

### New Capabilities

- `document-split`: 五策略切分、预览、segment 落库与父子元数据
- `document-embedding`: 任务生命周期、canary 写入、LangChain embed、Milvus（task_id + release_tag）

### Modified Capabilities

- （无）

## Impact

- **packages**: knowledge-content / knowledge-web / knowledge-common
- **data**: `knowledge_document_embedding_task`、`knowledge_document_segment`（含 release_tag）；无文档级 published task 指针
- **deps**: `pymilvus[model]>=2.6.9,<3.0.0`；`langchain-text-splitters>=1.1.1,<2.0.0`
- **docs**: `docs/rag/文档切分与向量化/`
