## Why

当前模型管理的能力字段（`support_reasoning`、`support_images`、`max_tokens`）靠用户手动填写，容易出错且不完整。LangChain 的 `init_chat_model` 已集成 models.dev 数据源，实例化后通过 `.profile` 可获取模型完整能力描述（推理、工具调用、结构化输出、模态支持、上下文窗口等）。应利用这一机制实现：用户填入 `model_code` + `provider` 后一键获取 Profile，自动回填能力字段，减少手工维护成本并为运行时自适应提供数据基础。

## What Changes

- 新增后端 `/ai/model/profile` 接口：按 `model_code` 查本地 models.dev 索引（与运行时 openai 兼容 provider 解耦），返回标准化能力字段；本地无缓存时首次查询尝试同步。
- 新增每日定时任务拉取 models.dev 并刷新本地索引。
- 扩展 `ai_models` 表，新增 Profile 能力字段：`support_tool_call`、`support_structured_output`、`max_input_tokens`、`input_modalities`、`output_modalities`。
- 新增系统字典 `ai_model_type`（llm / vlm / embedding / rerank），前端模型类型下拉与列表改用字典，不再硬编码。
- 前端模型表单新增「获取 Profile」按钮，调用接口后自动回填能力字段，用户可修改后保存；`embedding`/`rerank` 时隐藏 Profile 相关字段。
- DO/VO/DAO 层同步扩展新字段。

## Capabilities

### New Capabilities
- `model-profile`: 模型 Profile 自动获取与能力字段管理——后端接口、DB schema 扩展、前端自动回填交互。

### Modified Capabilities
- `ai-model-function-adapter`: 功能适配查询时可利用扩展后的 Profile 字段做更精确的模型能力匹配。

## Impact

- **DB**: `ai_models` 表 ALTER 新增列；`sys_dict_type` / `sys_dict_data` 新增 `ai_model_type`。
- **后端**: `knowledge-common`（DO/VO）、`knowledge-admin`（Controller/Service）新增接口与字段。
- **前端**: `knowledge-web` 模型管理表单与列表改用 `ai_model_type` 字典，并适配 Profile 字段。
- **依赖**: 依赖 LangChain `init_chat_model` 的 `.profile` 属性（当前 langchain 1.3.4 已支持）。
