## MODIFIED Requirements

### Requirement: 按功能点获取模型完整配置（参考需求文档 §10.3.5）
系统 SHALL 提供 `GET /api/admin/ai-model/function-adapter/config/{param_id}` 接口，按 `param_id` 联表查询 `ai_models` 返回模型完整配置，包括新增的 Profile 字段（`support_tool_call`、`support_structured_output`、`max_input_tokens`、`input_modalities`、`output_modalities`）。

#### Scenario: 查询适配配置含 Profile 字段
- **WHEN** 业务模块按 `param_id` 查询模型适配配置
- **THEN** 返回的 `AiModelConfigModel` SHALL 包含 `support_tool_call`、`support_structured_output`、`max_input_tokens`、`input_modalities`、`output_modalities` 字段
