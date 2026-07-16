# LangGraph 子图流式穿透与打字机效果处理

## 问题现象

使用子图架构的 LangGraph 应用中，前端始终无法展示打字机效果（逐 token 输出），所有 AI 消息和工具调用结果直到整个 Agent 执行完毕后才一次性推送到前端。

## 根因

子图边界阻断了两类流式事件：

| 事件模式 | 默认行为（`subgraphs=False`） | 期望行为 |
|---|---|---|
| `messages` | 子图内 LLM 的逐 token `AIMessageChunk` 被缓冲，子图结束后统一吐出**合并后的 `AIMessage`** | 实时透传每个 token chunk |
| `updates` | 子图内各节点（analyze / tools / collect_results）的更新被合并，子图结束后一次性 yield | 每执行完一个节点就 yield |

**本质：`stream_mode=['messages', 'updates']` 默认只在当前图的层内生效，子图被 LangGraph 框架当作黑盒黑盒处理。**

## 解决方案

### 核心：添加 `subgraphs=True` 参数

```python
# ❌ 错误：子图内 token 被拦截
async for item in compiled.astream(
    input_state, config=config,
    stream_mode=['messages', 'updates'],
):
    mode, data = item  # data 是合并后的完整 AIMessage
    ...

# ✅ 正确：子图内 token 逐块穿透
async for item in compiled.astream(
    input_state, config=config,
    stream_mode=['messages', 'updates'],
    subgraphs=True,  # 👈 关键参数
):
    ...
```

### 适配 3 元组输出格式

`subgraphs=True` 改变了 `astream()` 的 yield 格式：

```
# 无子图 / subgraphs=False: (mode, data)
('messages', (chunk, metadata))
('updates', {...})

# subgraphs=True: (namespaces, mode, data)
(('analysis:analyze',), 'messages', (chunk, metadata))
(('analysis:tools',),   'updates', {...})
(('analysis:collect_results',), 'updates', {...})
((), 'updates', {...})  # 父级 update（namespaces 为空）
```

适配代码：

```python
async for item in compiled.astream(..., subgraphs=True):
    if isinstance(item, tuple) and len(item) == 3:
        namespaces, mode, data = item
    else:
        namespaces, mode, data = (), *item  # 兼容无子图情况

    if mode == 'messages':
        chunk, metadata = data
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            yield _format_sse('token', {'content': chunk.content})

    elif mode == 'updates':
        # 跳过父级 updates（namespaces 为空），避免消息重复持久化
        if not namespaces:
            continue
        for node_name, update in data.items():
            await _persist_node_messages(update.get('messages', []), ...)
            for event_type, event_data in _map_node_output_to_sse(update):
                if event_type == 'token':
                    continue  # token 已由 messages 模式实时处理
                yield _format_sse(event_type, event_data)
```

## 输出格式对比

```
subgraphs=False                          subgraphs=True
─────────────────────                    ─────────────────────
                                        (('analysis:analyze',), 'messages', chunk)
                                        (('analysis:analyze',), 'messages', chunk)
                                        (('analysis:analyze',), 'messages', chunk)
                                        ... 逐 token 透传 ...
(('analysis:tools',), 'updates', {⋯})   (('analysis:tools',), 'updates', {⋯})
(('analysis:analyze',), 'updates', {⋯}) (('analysis:analyze',), 'updates', {⋯})
... 一批 yield ...                       ... 逐个 yield ...
(('analysis:collect_results',), updates)
(('analysis:analyze',), updates)
(() , 'updates', parent_level)          (() , 'updates', parent_level)
```

左侧 `subgraphs=False` 时 `messages` 模式完全不 yield token 事件，只显示 `updates`。右侧 `subgraphs=True` 时，`(analysis:analyze, messages, chunk)` 逐条透传。

## 配套改造

### 1. Node 内部需要改为流式调用 LLM

```python
# ❌ 错误：ainvoke 阻塞等待完整响应
response = await llm.ainvoke(messages)

# ✅ 正确：astream 逐 chunk 聚合
merged = None
async for chunk in llm.astream(messages):
    if merged is None:
        merged = chunk
    else:
        merged += chunk
response = merged if merged is not None else AIMessage(content='')
```

> 注意：纵使 `stream_mode='messages'` 已捕获 token 事件，但 Node 函数本身仍需要返回完整的 `AIMessage` 作为状态更新，否则子图状态会丢失 LLM 输出。

### 2. 前端需要在流结束时提交剩余内容

```javascript
// finally 块中提交残留的 streamingContent
} finally {
    if (streamingContent.value) {
        messages.value.push({ role: 'ai', content: streamingContent.value });
        streamingContent.value = '';
    }
    streaming.value = false;
}
```

## 关键约束

| 约束 | 说明 |
|---|---|
| `subgraphs=True` 必须配合 `stream_mode` 使用 | 仅 `stream_mode=['messages', 'updates']` 双模态时效果最完整 |
| 父级 `updates` 需跳过 | `namespaces` 为空时代表父图整轮结束，跳过以避免重复持久化 |
| `AIMessageChunk` 可合并 | `+=` 操作符将多个 `AIMessageChunk` 合并为完整 `AIMessage` |
| Checkpointer 绑定在父图 | 子图不绑定 Checkpointer，由父图统一管理持久化 |

## 排查 Checklist

- [ ] `astream()` 参数是否包含 `subgraphs=True`？
- [ ] 是否适配了 `(namespaces, mode, data)` 3 元组格式？
- [ ] Node 内部是否用 `astream()` 替代 `ainvoke()` 聚合？
- [ ] `updates` 模式中是否跳过 `namespaces` 为空的父级事件？
- [ ] 前端是否在 `finally` 中提交残留的 `streamingContent`？
- [ ] SSE 事件中 `token` 事件是否只由 `messages` 模式 yield，`updates` 模式跳过？
