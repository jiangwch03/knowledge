## Why

当前 RAG 知识库数据主要依赖人工整理，缺少对 PDF/DOCX/XLSX/TXT/MD 等常见业务文档的快速归集通道。建设资料上传解析能力可以显著提升知识库数据入库效率，统一文档版本与解析状态管理，并为后续分块、向量化提供标准化的 Markdown 数据源。

## What Changes

- 在 `knowledge-web` 前端新增「知识管理 → 资料上传」独立页面（参考需求文档 §4.1 / §4.2 / §4.3 / §4.4 / §4.5）。
- 在 `knowledge-rag` 后端实现文件上传、总页数解析、版本预占、MinerU 解析调度、TXT 转 Markdown、解析结果合并入库、失败重试与用户决策等全链路能力（参考需求文档 §5 / §6）。
- 在 `knowledge-common` 中下沉 `knowledge_ai_models` 的 DO/DAO/VO，供 `knowledge-admin` 与 `knowledge-rag` 共享（参考需求文档 §9.2 / §10.2.1）。
- 在 `knowledge-admin` 中新增模型功能适配管理接口与页面，并负责 `merio_language` 字典初始化（参考需求文档 §8.1 / §10）。
- 新增 5 张数据表：`knowledge_document`、`knowledge_upload_document_record`、`knowledge_mineru_parse_task`、`knowledge_mineru_parse_detail_task`、`knowledge_ai_model_function_adapter`（参考需求文档 §7）。

## Capabilities

### New Capabilities

- `rag-document-upload`: RAG 资料上传主能力，包含文件上传、版本预占、MinerU 解析调度、TXT 转 Markdown、解析任务详情、用户决策、文档预览/下载/删除等。
- `ai-model-function-adapter`: 模型功能适配管理，支持将业务功能点（如 TXT 生成 Markdown）与具体大模型配置绑定，供业务模块按参数 ID 动态读取模型。

### Modified Capabilities

- 无

## Impact

- **前端**: `knowledge-web` 新增菜单、页面、API 封装、路由与权限编码。
- **后端**: `knowledge-rag` 新增 Controller/Service/DAO/VO、消息流消费者、定时任务；`knowledge-admin` 新增模型功能适配接口与字典初始化 SQL。
- **公共组件**: `knowledge-common` 下沉 `knowledge_ai_models` 相关 DO/DAO/VO，并调整 `knowledge-admin` 的 import 路径。
- **数据库**: 新建 5 张表及索引；需补充字典与模型功能适配初始化数据。
- **基础设施**: 依赖 MinIO、MinerU API、消息流（Kafka/Redis）、LangChain 1.2.X（大模型调用框架）。
