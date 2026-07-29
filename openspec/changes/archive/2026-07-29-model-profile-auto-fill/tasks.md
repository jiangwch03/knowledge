## 1. DB Schema 升级

- [x] 1.1 编写 `sql/04_upgrade_model_profile.sql`：ALTER `ai_models` 表新增 `support_tool_call`、`support_structured_output`、`max_input_tokens`、`input_modalities`、`output_modalities` 列
- [x] 1.2 同文件新增字典 `ai_model_type`：`sys_dict_type` + `sys_dict_data`（llm / vlm / embedding / rerank）
- [x] 1.3 更新 `sql/README.md` 补充新 SQL 文件说明

## 2. 后端 DO/VO 层扩展

- [x] 2.1 `ai_models_do.py`：`AiModels` 类新增 `support_tool_call`、`support_structured_output`、`max_input_tokens`、`input_modalities`、`output_modalities` 列定义
- [x] 2.2 `ai_model_vo.py`：`AiModelModel` 新增对应字段
- [x] 2.3 新增 `ModelProfileVo`（Pydantic 模型），定义 Profile 接口返回结构
- [x] 2.4 `ai_model_function_adapter_vo.py`：`AiModelConfigModel` 新增 Profile 扩展字段

## 3. 后端 Profile 获取接口（knowledge-admin）

- [x] 3.1 在 `knowledge-admin` 新增 `ModelsDevProfileService`：拉取/缓存 models.dev，按 `model_code` 建本地索引并映射为 `ModelProfileVo`
- [x] 3.2 在 `ai_model_service.py` 的 `get_model_profile`：若 `modelType` 为 `rerank`/`embedding` 直接返回空 VO；否则查本地 models.dev 索引
- [x] 3.3 在 `ai_model_controller.py` 新增 `GET /ai/model/profile` 接口，接收 `modelCode` + `provider`（+ 可选 `modelType`）参数，调用 service 返回 Profile
- [x] 3.4 新增定时任务 `sync_models_dev_profiles`（每天 03:00）+ `sql/05_models_dev_profile_sync.sql` 注册 sys_job

## 4. 后端适配层扩展

- [x] 4.1 `ai_model_function_adapter_dao.py`：联表查询 SQL 补充新增 Profile 字段
- [x] 4.2 `ai_model_function_adapter_vo.py`：`AiModelConfigModel` 序列化适配

## 5. 前端表单改造

- [x] 5.1 `model.js`：新增 `getModelProfile(modelCode, provider, modelType)` API 方法
- [x] 5.2 `index.vue`：模型类型改为 `useDict('ai_model_type')` 驱动下拉与列表 `dict-tag`，删除硬编码 `el-option` 与 `MODEL_TYPE_LABELS`
- [x] 5.3 `index.vue` 表单区：新增 Profile 能力字段（supportToolCall、supportStructuredOutput、maxInputTokens、inputModalities、outputModalities）
- [x] 5.4 `index.vue` 表单区：新增「获取 Profile」按钮，点击调用 API 回填表单，含校验与错误提示
- [x] 5.5 `index.vue` 表单区：按 `modelType` 条件渲染——`rerank`/`embedding` 时隐藏 Profile 字段区域和「获取 Profile」按钮；切换类型时清空 Profile 字段
- [x] 5.6 `index.vue` 列表页：列表列适配新增字段展示
- [x] 5.7 `reset()` 方法补充新字段默认值

## 6. 测试验证

- [ ] 6.1 手动验证：填写 `gpt-4o` + `openai` 获取 Profile，确认回填正确
- [ ] 6.2 手动验证：填写私有模型获取 Profile，确认优雅降级（提示手动填写）
- [ ] 6.3 手动验证：新增/修改模型保存 Profile 字段，确认 DB 持久化
- [ ] 6.4 手动验证：模型类型字典含 rerank；选 embedding/rerank 时 Profile 字段隐藏
