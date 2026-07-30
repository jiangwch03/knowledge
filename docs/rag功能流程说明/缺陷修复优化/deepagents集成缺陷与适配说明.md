# deepagents state / context 适配

## 背景

爬虫督导 Agent 用 deepagents（`create_deep_agent`），规划子 Agent 靠内置 `task` 委派。业务字段（如目标网址、任务 ID）应在 state 里跨轮次保留；`model_id` 等只在单次 invoke 的 context 里。

## 原因

`create_deep_agent` 只暴露 `context_schema`，内部调用 `create_agent` 时**不传 `state_schema`**。

- `state_schema`：决定 checkpointer / `runtime.state` 有哪些 key；`task` 从这里拷贝字段给子 Agent
- `context_schema`：仅单次 invoke 的 runtime context，**不会**进 `runtime.state`

若把 `SupervisorState` 误传成 `context_schema`：督导内部 `runtime.state` 往往只剩 `messages`，规划子 Agent 拿不到业务字段。

另：`task` 委派时不会原样带上督导对话历史（`messages` 被排除），只用 description 生成一条新消息。

## 修复

构建时把 deepagents 传入的 schema 映射为真正的 `state_schema`，另指定 context：

```python
def _create_agent_with_state_schema(*args, **kwargs):
    context_schema = kwargs.pop('context_schema', None)
    if context_schema is not None:
        kwargs['state_schema'] = context_schema       # 业务 state
    kwargs['context_schema'] = AgentIdentityContext   # model_id 等
    return create_agent(*args, **kwargs)
```

实现：`knowledge_content/agents/crawler_agent/workers/supervisor/deep_agent.py`  
验证：`knowledge-content/scripts/demo_context_model_id.py`

升级 deepagents 若官方区分 `state_schema` / `context_schema`，可评估去掉该映射。
