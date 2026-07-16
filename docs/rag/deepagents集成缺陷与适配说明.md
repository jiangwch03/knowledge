# deepagents 集成缺陷与适配说明

> 验证脚本：`knowledge-content/scripts/demo_context_model_id.py`（Part 3 / Part 4）

## 一、背景

爬虫 Agent Supervisor 使用 LangChain **deepagents**（`create_deep_agent` + `SubAgentMiddleware`），Planning 通过内置 **`task` 工具**委派。

父图结构（`graph.py`）：

```
StateGraph(SupervisorState, context_schema=CrawlerAgentContext)
  url_preprocess → supervisor(deepagents) → state_sync → END
```

业务数据分两层：

| 层级 | 载体 | 典型字段 | 生命周期 |
|------|------|----------|----------|
| **state** | checkpointer 持久化 | `target_url`, `task_id`, `strategy_config`, `session_id`… | 跨轮次 |
| **context** | 单次 invoke 注入 | `model_id` | 单次对话轮次内不变 |

---

## 二、deepagents 核心缺陷

### 2.1 只暴露 `context_schema`，没有 `state_schema`

`create_deep_agent(..., context_schema=SupervisorState)` 最终调用：

```python
create_agent(..., context_schema=context_schema)  # 不传 state_schema
```

LangGraph `create_agent` 中：

- **`state_schema`**：决定图内存/checkpointer 里有哪些 key，`SubAgentMiddleware.task` 从 **`runtime.state`** 拷贝业务字段给子 Agent。
- **`context_schema`**：仅声明单次 invoke 的 runtime context（如 `model_id`），**不会**把字段放进 `runtime.state`。

因此若只传 `context_schema=SupervisorState` 而不映射为 `state_schema`：

- 父图传入的 `target_url` / `session_id` 等会在 Supervisor **内部**丢失；
- `task` 工具执行时 `runtime.state` 往往只剩 `messages`；
- Planning 子 Agent 收不到业务字段。

**demo 验证（Part 4，无 hack）：**

```
[父图 url_preprocess]  state 有 target_url ✓
[deepagents 内部 peek] runtime.state=（空）  ← task 实际看到的
[Planning]             target_url=None
```

### 2.2 `task` 工具不传 `context` kwarg

`SubAgentMiddleware` 委派子 Agent 时：

```python
subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
subagent_state["messages"] = [HumanMessage(content=description)]
result = await subagent.ainvoke(subagent_state)  # 无 context=
```

- **state**：从 `runtime.state` 拷贝（依赖 2.1 的 `state_schema` 正确）。
- **context**：子 Agent `ainvoke` 未显式传参；**同一次父图 invoke 内** LangGraph 会通过 runtime 继承顶层 `context`（如 `model_id`），Planning middleware 仍可读到。

### 2.3 父图边界 vs 子图内部 state 不一致

父图 `StateGraph(SupervisorState)` 在 **子图节点出入口** 可能仍看到完整 state，但 **deepagents 内部** `create_agent` 若无 `state_schema`，工具节点里的 `runtime.state` 已是阉割版。

不能以「父图 state_sync 还有 target_url」推断 task 能拷贝给 Planning——必须以 **Supervisor 内部** `runtime.state` 为准。

### 2.4 `messages` 不参与 task 拷贝

`_EXCLUDED_STATE_KEYS` 含 `messages`；task 会用 **description 参数** 替换为单条 `HumanMessage`，Supervisor 对话历史不会原样进 Planning。

---

## 三、本项目适配方案（生产代码 hack）

`deep_agent.py` 在构建时对 `deepagents.graph.create_agent` 做 **runtime 映射**：

```python
def _create_agent_with_state_schema(*args, **kwargs):
    context_schema = kwargs.pop('context_schema', None)
    if context_schema is not None:
        kwargs['state_schema'] = context_schema      # SupervisorState → state
    kwargs['context_schema'] = CrawlerAgentContext   # model_id → context
    return create_agent(*args, **kwargs)

create_deep_agent(..., context_schema=SupervisorState)
```

实现位置：`knowledge-content/.../workers/supervisor/deep_agent.py`

### 字段分工（当前约定）

| 字段 | 存放位置 | 注入方式 |
|------|----------|----------|
| `model_id` | `CrawlerAgentContext` | `astream(..., context={'model_id': vo.model_id})` |
| `target_url`, `task_id`, `strategy_config`, 会话审计字段 | `SupervisorState` | 父图 input / checkpointer |
| Planning 专用 `mode`, `fix_reason` | `PlanningState` | task description / 同名 key 回流 |

---

## 四、验证清单

```bash
cd knowledge-content && ../.venv/bin/python scripts/demo_context_model_id.py
```

| Part | 验证点 |
|------|--------|
| 1 | context.model_id 顶层注入与同 invoke 继承 |
| 2 | task 拷贝 state、Command 回流 strategy_config |
| 3 | 单独 create_agent：无 state_schema 时业务字段丢失 |
| 4 | **父图 → deepagents 子图**：无/有 state_schema 时内部 `runtime.state` 差异 |

Part 4 有 hack（显式 state_schema）预期：

```
[deepagents 内部 peek] runtime.state={target_url, session_id, ...}, context.model_id=888
[Planning] target_url='https://example.com'
```

---

## 五、后续若升级 deepagents

若官方 `create_deep_agent` 增加 `state_schema` 参数或正确区分 state/context，可评估改回 `create_deep_agent` 以减少中间件栈手工组装；升级前务必重跑上述 demo。
