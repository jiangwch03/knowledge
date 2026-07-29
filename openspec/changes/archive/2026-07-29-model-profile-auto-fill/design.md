## Context

当前 `ai_models` 表仅有 `support_reasoning`（Y/N）、`support_images`（Y/N）、`max_tokens` 三个能力字段，由用户手工填写。LangChain ≥1.3 的 `init_chat_model` 返回的 `BaseChatModel` 实例已支持 `.profile` 属性，底层数据来源为 models.dev 开源项目，覆盖模型能力、上下文窗口、模态支持等元数据。

项目已有 `LangChainModelFactory`，使用 `init_chat_model` 创建模型实例。可复用此工厂获取 Profile。

## Goals / Non-Goals

**Goals:**
- 新增 `GET /ai/model/profile` 接口，根据 `model_code` 从本地 models.dev 索引获取 Profile 并返回标准化能力字段（运行时仍可用 openai 兼容协议，不强制厂商 SDK）。
- 本地缓存 models.dev 数据，并由定时任务每日同步。
- 扩展 `ai_models` 表和 DO/VO 层，持久化 Profile 能力字段。
- 模型类型改为系统字典 `ai_model_type` 维护（含 `rerank`），前端下拉/列表统一走字典。
- 前端模型表单新增「获取 Profile」按钮，自动回填能力字段，用户可修改后保存。

**Non-Goals:**
- 不为 Profile 引入 langchain-deepseek 等厂商 SDK。
- 不改变 `knowledge_ai_model_function_adapter` 的业务逻辑（仅字段可见性扩展）。
- 不做 Embedding / Rerank 模型的 Profile 获取。

## Decisions

### D1: Profile 获取方式 — 本地 models.dev 索引（按 model_code）

**选择**: 管理端维护 models.dev 本地索引（上传目录 `models_dev/profile_index.json`）。`get_model_profile` 按 `model_code` 查询；同名模型优先取官方源（openai/deepseek/alibaba-cn 等），聚合网关靠后。定时任务每日 03:00 拉取 `https://models.dev/api.json` 刷新索引；本地无缓存时首次查询会尝试同步一次。

**理由**: 项目运行时普遍使用 `provider=openai` 兼容协议以避免厂商 SDK；LangChain `.profile` 绑死当前 provider 包目录，导致 deepseek-chat/qwen-plus 等拿不到数据。本地 models.dev 索引与运行时 provider 解耦。

**备选**: `init_chat_model` + 厂商 SDK；或每次远程查 models.dev（强依赖外网）。

### D2: Profile 字段映射

LangChain `.profile` 返回的字段映射到 `ai_models` 表新增列：

| Profile 字段 | DB 列 | 类型 | 说明 |
|---|---|---|---|
| `max_input_tokens` | `max_input_tokens` | INT | 最大输入 token（上下文窗口） |
| `max_output_tokens` | — | 复用现有 `max_tokens` | 最大输出 token |
| `tool_calling` | `support_tool_call` | CHAR(1) Y/N | 工具调用 |
| `structured_output` | `support_structured_output` | CHAR(1) Y/N | 结构化输出 |
| `reasoning_output` | — | 复用现有 `support_reasoning` | 推理 |
| `image_inputs` | — | 复用现有 `support_images` | 图片输入 |
| `input_modalities` | `input_modalities` | VARCHAR(255) | 输入模态 JSON 数组 |
| `output_modalities` | `output_modalities` | VARCHAR(255) | 输出模态 JSON 数组 |

**理由**: 布尔能力用 CHAR(1) Y/N 与现有字段风格一致；模态列表用 JSON 字符串存储，前端 tag 展示。复用已有 `max_tokens`、`support_reasoning`、`support_images` 避免重复列。

### D3: 前端交互流程

1. 用户填写 `modelCode` + `provider` 后，点击「获取 Profile」按钮。
2. 前端调用 `GET /ai/model/profile?modelCode=xxx&provider=yyy`。
3. 后端返回 Profile VO → 前端自动回填表单字段（max_tokens、temperature、各 support_* 等）。
4. 用户可修改回填值后提交保存。
5. 若获取失败（模型不在 models.dev 或 provider 不支持），前端提示「未获取到 Profile，请手动填写」，不阻断流程。

### D4: 优雅降级

`.profile` 可能为 None（旧版 LangChain 或私有模型）。接口返回空 Profile VO，前端不回填，用户手动填写。不抛异常。

### D5: 模型类型字典化（`ai_model_type`）

**选择**: 新增系统字典 `ai_model_type`，与现有 `ai_provider_type` 同模式：

| dict_value | dict_label |
|---|---|
| `llm` | 大语言模型 |
| `vlm` | 视觉语言模型 |
| `embedding` | 向量模型 |
| `rerank` | 精排模型 |

前端：
- 表单下拉、列表展示统一 `useDict('ai_model_type')` + `dict-tag`。
- 删除硬编码 `el-option` 与 `MODEL_TYPE_LABELS`。

**理由**: 当前前端写死 llm/vlm/embedding，DB 已有 `rerank` 种子数据却无法在管理端选择；字典化后可在字典管理里扩展类型，无需改前端代码。

### D6: Rerank / Embedding 等非 ChatModel 类型隐藏 Profile 字段

Rerank / Embedding 不是 ChatModel，`init_chat_model` 会报错，且不支持 `.profile`。

**选择**:
- 前端按 `modelType` 条件渲染：`llm` / `vlm` 显示 Profile 字段 +「获取 Profile」；`embedding` / `rerank` 隐藏全部 Profile 能力字段与按钮。
- 后端若 `modelType` 为 `embedding` / `rerank`，直接返回空 Profile，不调用 `init_chat_model`。
- 隐藏判定用前端常量集合（如 `NO_PROFILE_MODEL_TYPES = ['embedding', 'rerank']`），与字典解耦——字典管展示文案，常量管是否支持 Profile。若后续新增类型需隐藏，改常量即可。

## Risks / Trade-offs

- **[Profile 数据准确性]** → models.dev 是社区维护，部分模型数据可能滞后。用户可在回填后手动修正。
- **[LangChain 版本依赖]** → `.profile` 属性需 langchain ≥1.3。当前版本 1.3.4 已满足。升级时关注 breaking change。
- **[私有/自部署模型无 Profile]** → 优雅降级为手动填写，不影响现有功能。
