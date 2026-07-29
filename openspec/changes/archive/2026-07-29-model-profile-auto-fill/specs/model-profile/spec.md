## ADDED Requirements

### Requirement: 获取模型 Profile 接口
系统 SHALL 提供 `GET /api/admin/ai/model/profile` 接口，根据 `modelCode` 从本地 models.dev 索引获取模型能力 Profile，返回标准化的能力字段 VO。运行时 provider（如 openai 兼容）不阻止按 model_code 命中官方源数据。

#### Scenario: 成功获取 Profile（openai 兼容模型）
- **WHEN** 管理员传入有效的 `modelCode`（如 `deepseek-chat`）和 `provider`（如 `openai`）
- **THEN** 系统从本地 models.dev 索引按 `modelCode` 查询（优先官方源），返回包含 `maxTokens`、`maxInputTokens`、`supportReasoning`、`supportImages`、`supportToolCall`、`supportStructuredOutput` 等字段的 Profile VO

#### Scenario: 模型无 Profile 数据
- **WHEN** 管理员传入的模型在本地 models.dev 索引中无记录
- **THEN** 系统返回空 Profile VO（所有字段为 null），不抛异常

#### Scenario: 本地索引缺失时首次同步失败
- **WHEN** 本地无索引且远程拉取 models.dev 失败
- **THEN** 系统返回空 Profile VO（或错误提示「获取 Profile 失败: {原因}」），不阻断表单手工填写

#### Scenario: 非 ChatModel 类型（rerank / embedding）
- **WHEN** 管理员传入的 `modelType` 为 `rerank` 或 `embedding`
- **THEN** 系统直接返回空 Profile VO，不查询索引

### Requirement: models.dev 本地索引每日同步
系统 SHALL 通过定时任务每日拉取 `https://models.dev/api.json`，刷新本地 Profile 索引文件。

#### Scenario: 每日同步成功
- **WHEN** 到达 cron（默认每天 03:00）且 admin Leader 调度器运行
- **THEN** 系统下载 models.dev 数据、重建 `profile_index.json`，并更新同步元数据

#### Scenario: 同步失败不影响已有索引
- **WHEN** 定时同步网络或解析失败
- **THEN** 系统记录错误日志，保留上一份本地索引供查询

### Requirement: ai_models 表 Profile 字段扩展
系统 SHALL 在 `ai_models` 表新增以下列，持久化模型 Profile 能力数据：
- `support_tool_call` CHAR(1) DEFAULT 'N' — 是否支持工具调用
- `support_structured_output` CHAR(1) DEFAULT 'N' — 是否支持结构化输出
- `max_input_tokens` INT — 最大输入 token 数（LangChain 语义为上下文窗口）
- `input_modalities` VARCHAR(255) — 输入模态 JSON 数组
- `output_modalities` VARCHAR(255) — 输出模态 JSON 数组

#### Scenario: 新增模型时保存 Profile 字段
- **WHEN** 管理员通过新增接口提交包含 Profile 字段的模型数据
- **THEN** 系统将 Profile 字段写入 `ai_models` 表

#### Scenario: 修改模型时更新 Profile 字段
- **WHEN** 管理员通过修改接口更新 Profile 字段
- **THEN** 系统更新 `ai_models` 表对应列

### Requirement: 前端 Profile 自动回填
系统 SHALL 在模型管理表单中提供「获取 Profile」按钮，用户填写 `modelCode` + `provider` 后点击，自动调用接口回填能力字段。

#### Scenario: 回填成功
- **WHEN** 用户已填写 `modelCode` 和 `provider`，点击「获取 Profile」
- **THEN** 前端调用 `/ai/model/profile` 接口，将返回的 Profile 数据回填到表单各能力字段（maxTokens、supportReasoning、supportImages、supportToolCall、supportStructuredOutput、maxInputTokens、inputModalities、outputModalities）

#### Scenario: 回填失败
- **WHEN** Profile 接口返回空数据或错误
- **THEN** 前端提示「未获取到模型 Profile，请手动填写」，不阻断表单提交

#### Scenario: 未填写必要参数
- **WHEN** 用户未填写 `modelCode` 或 `provider` 就点击「获取 Profile」
- **THEN** 前端提示「请先填写模型编码和提供商」

### Requirement: 模型类型字典化
系统 SHALL 新增字典类型 `ai_model_type`，包含 `llm`（大语言模型）、`vlm`（视觉语言模型）、`embedding`（向量模型）、`rerank`（精排模型）。前端模型管理的类型下拉与列表展示 SHALL 使用该字典，不再硬编码选项或标签映射。

#### Scenario: 表单下拉使用字典
- **WHEN** 管理员打开新增/修改模型表单
- **THEN** 模型类型下拉选项来自字典 `ai_model_type`，包含 llm / vlm / embedding / rerank

#### Scenario: 列表展示使用字典标签
- **WHEN** 管理员查看模型列表
- **THEN** 模型类型列通过 `dict-tag` 展示字典标签（如 `rerank` 显示为「精排模型」）

### Requirement: 按模型类型隐藏 Profile 字段
前端 SHALL 根据 `modelType` 动态控制 Profile 相关字段的可见性。当 `modelType` 为 `rerank` 或 `embedding` 时，隐藏 Profile 能力字段区域和「获取 Profile」按钮。

#### Scenario: ChatModel 类型显示 Profile 字段
- **WHEN** 用户选择 `modelType` 为 `llm` 或 `vlm`
- **THEN** 表单显示全部 Profile 能力字段（supportReasoning、supportImages、supportToolCall、supportStructuredOutput、maxTokens、maxInputTokens、inputModalities、outputModalities）和「获取 Profile」按钮

#### Scenario: 非 ChatModel 类型隐藏 Profile 字段
- **WHEN** 用户选择 `modelType` 为 `rerank` 或 `embedding`
- **THEN** 表单隐藏所有 Profile 能力字段和「获取 Profile」按钮

#### Scenario: 模型类型切换时清空 Profile 字段
- **WHEN** 用户将 `modelType` 从 `llm`/`vlm` 切换为 `rerank`/`embedding`
- **THEN** 前端清空已回填的 Profile 能力字段值
