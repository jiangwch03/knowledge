# LangGraph 子图流式穿透（打字机无效果）

## 背景

Agent 使用子图后，前端看不到打字机效果：AI 正文和工具结果要等整轮跑完才一次性推送。

## 原因

`astream(..., stream_mode=['messages', 'updates'])` **默认不穿透子图**（`subgraphs=False`）。子图被当成黑盒：

- `messages`：子图内 token 被缓冲，结束后才吐出合并后的完整消息
- `updates`：子图内节点更新被合并，结束后一次性 yield

## 修复

1. **`astream` 打开子图穿透**，并适配三元组输出：

```python
async for item in compiled.astream(
    input_state,
    config=config,
    stream_mode=['messages', 'updates'],
    subgraphs=True,
):
    # subgraphs=True → (namespaces, mode, data)
    # subgraphs=False → (mode, data)
    if isinstance(item, tuple) and len(item) == 3:
        namespaces, mode, data = item
    else:
        namespaces, mode, data = (), *item

    if mode == 'messages':
        # 实时推 token
        ...
    elif mode == 'updates':
        if not namespaces:
            continue  # 跳过父级 updates，避免重复落库
        ...
```

2. **节点内用 `llm.astream` 聚合**，不要只 `ainvoke`（否则框架层也拿不到逐 token）。节点返回值仍须是完整 `AIMessage`，供状态更新。

当前实现见 `knowledge_common/agent/stream/normalizer.py`（已设 `subgraphs=True`）。
