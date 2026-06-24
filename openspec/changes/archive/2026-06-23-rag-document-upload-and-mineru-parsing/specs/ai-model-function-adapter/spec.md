## ADDED Requirements

### Requirement: 模型功能适配列表分页查询（参考需求文档 §10.3.1）
系统 SHALL 提供 `GET /api/admin/ai-model/function-adapter/list` 接口，分页查询模型功能适配记录并关联模型名称与编码。

#### Scenario: 分页查询适配列表
- **WHEN** 管理员请求模型功能适配列表
- **THEN** 系统按 `del_flag='0'` 查询 `knowledge_ai_model_function_adapter`，联表 `knowledge_ai_models` 返回分页结果

#### Scenario: 按功能点或参数 ID 查询
- **WHEN** 管理员传入 `function_point` 模糊查询或 `param_id` 精确查询
- **THEN** 系统按条件过滤并返回适配列表

### Requirement: 新增模型功能适配（参考需求文档 §10.3.2）
系统 SHALL 提供 `POST /api/admin/ai-model/function-adapter` 接口，新增业务功能点与模型的适配关系。

#### Scenario: 正常新增适配记录
- **WHEN** 管理员传入 `function_point`、`param_id`、`model_id`，且 `param_id` 唯一、模型存在且启用
- **THEN** 系统在 `knowledge_ai_model_function_adapter` 中插入新记录

#### Scenario: param_id 重复
- **WHEN** 管理员传入已存在的 `param_id`
- **THEN** 系统返回唯一性校验错误

#### Scenario: 模型不存在或已停用
- **WHEN** 管理员传入不存在或已停用的 `model_id`
- **THEN** 系统返回模型校验错误

### Requirement: 修改模型功能适配（参考需求文档 §10.3.3）
系统 SHALL 提供 `PUT /api/admin/ai-model/function-adapter/{adapter_id}` 接口，修改适配记录。

#### Scenario: 正常修改适配记录
- **WHEN** 管理员传入 `function_point`、`param_id`、`model_id`，且记录存在、未删除、`param_id` 唯一（排除自身）、模型存在且启用
- **THEN** 系统更新对应适配记录

#### Scenario: 修改不存在的适配记录
- **WHEN** 管理员传入不存在的 `adapter_id`
- **THEN** 系统返回记录不存在错误

### Requirement: 删除模型功能适配（参考需求文档 §10.3.4）
系统 SHALL 提供 `DELETE /api/admin/ai-model/function-adapter/{adapter_id}` 接口，软删除适配记录。

#### Scenario: 正常删除适配记录
- **WHEN** 管理员传入存在的 `adapter_id`
- **THEN** 系统将对应记录 `del_flag` 更新为 `'2'`，并更新 `update_by`/`update_time`

### Requirement: 根据参数 ID 获取模型配置（参考需求文档 §10.3.5 / §10.4）
系统 SHALL 提供 `GET /api/admin/ai-model/function-adapter/{param_id}/model` 接口，返回参数 ID 绑定的完整模型配置。

#### Scenario: 正常获取模型配置
- **WHEN** 业务模块传入已配置的 `param_id`
- **THEN** 系统联表返回 `knowledge_ai_models` 的 `model_code`、`provider`、`api_key`、`base_url` 等配置

#### Scenario: 参数 ID 未配置
- **WHEN** 业务模块传入未配置的 `param_id`
- **THEN** 系统返回配置不存在错误

### Requirement: 大模型配置表下沉共享（参考需求文档 §9.2 / §10.2.1）
系统 SHALL 将 `knowledge_ai_models` 的 DO/DAO/VO 从 `knowledge-admin` 下沉至 `knowledge-common`，供 `knowledge-admin` 与 `knowledge-content` 共享。

#### Scenario: 调整 import 路径
- **WHEN** 迁移完成后
- **THEN** `knowledge-admin` 原有业务代码中 `knowledge_ai_models` 的 import 路径指向 `knowledge-common`
