# StreamingResponse 异常静默失败修复

## 问题现象

重启项目后，点击「确认分析」按钮，前端**没有任何报错提示**，也无任何响应，静默失败。

后端日志报：

```
RuntimeError: Caught handled exception, but response already started.
```

## 根因分析

### 1. 调用链路

前端 `handleUserChoice` → `fetch(POST /crawler/chat/{session_id}/resume)` → Controller 返回 `StreamingResponse(CrawlerAgentService.resume_stream(...), media_type='text/event-stream')`。

### 2. StreamingResponse 的工作原理

`StreamingResponse` 的处理时序如下：

```
1. ASGI send({"type": "http.response.start", "status": 200, "headers": {...}})
   └── 此时 HTTP headers 已发出（status=200, Content-Type=text/event-stream）
2. async for chunk in self.body_iterator:  ← 开始遍历 async generator
   └── 此时 generator 才开始执行
```

即：**headers 在 generator 开始执行之前就已经发送给客户端了**。

### 3. 异常处理的冲突

当 `resume_stream` 检测到无 pending interrupt 时：

```python
if not has_pending_interrupt:
    raise ServiceException(...)
```

- 此时 Stream 已经建立（headers 已发送）
- FastAPI 全局异常处理器 `service_exception_handler` 试图返回 `ResponseUtil.error(msg=...)` 作为响应
- 但 Starlette 检测到 response 已经开始，拒绝修改已发送的 headers
- 抛出 `RuntimeError: Caught handled exception, but response already started.`

### 4. 前端表现

- `fetch()` 收到 HTTP 200 响应（正常）
- `_readSseStream()` 开始读取 body
- 由于 generator 异常中断，body 被截断，**没有合法 SSE 事件**
- `parseSseBlock` 因匹配不到 `event:` 和 `data:` 前缀，**每条数据都被 silently 跳过**
- 函数正常结束，catch 块未命中
- 用户看到的是**完全静默的失败**——无报错、无输出、无提示

## 修复方案

将 `resume_stream` 中 `raise ServiceException` 的行为改为 **yield SSE `error` 事件**，使错误信息通过已建立的 SSE 通道推送给前端。

### 修改点

**文件：** `knowledge-content/src/knowledge_content/agents/service/crawler_agent_service.py`

1. **移除 `raise ServiceException`**，改为：
   ```python
   yield _format_sse('error', {'message': error_msg})
   return
   ```

2. **添加全局 `try-except` 兜底**，捕获所有意外异常，统一转换为 SSE `error` 事件：
   ```python
   except Exception as e:
       logger.opt(exception=True).error('[AgentResume] 中断恢复执行异常: {}', e)
       yield _format_sse('error', {'message': '[AgentResume] 中断恢复异常,服务器异常,请联系运维处理'})
   ```

3. **清理不再使用的 `ServiceException` import**

### 为什么这样可以工作

前端 `parseSseBlock` 已支持 `error` 事件：

```javascript
} else if (event === 'error') {
    _commitStreamingAiMessage();
    ElMessage.error(data.message || 'Agent 执行出错');
    console.warn('[SSE] Agent error event:', data);
}
```

以 SSE `error` 事件推送错误信息，前端会在页面上弹出 `ElMessage.error()` 提示框，错误不再被静默吞噬。

## 影响范围

### 修改的文件

- `knowledge-content/src/knowledge_content/agents/service/crawler_agent_service.py`

### 修复的方法

| 方法 | 问题 | 修复方式 |
|------|------|----------|
| `resume_stream` | `raise ServiceException` 导致 `RuntimeError` | 改为 `yield SSE error` + 全局 try-except |
| `chat_stream` | 步骤 3（`get_root_graph()`）和步骤 5（`_check_post_interrupt`）在 yield 后无异常保护 | 添加全局 try-except 兜底 |

### 其他 StreamingResponse 端点

| 端点 | 状态 | 说明 |
|------|------|------|
| `AiChatService.chat_services()` | ✅ 安全 | 内部 `_stream_agent` 已有全局 try-except 并 yield error 事件 |
| 各 Export 端点 (dict/job/config/log等) | ✅ 低风险 | 使用 `ResponseUtil.streaming()` 返回文件流，非 async generator 模式 |
| 文件下载端点 (common/download) | ✅ 低风险 | 使用 `ResponseUtil.streaming()` 返回文件流，非 async generator 模式 |

## 经验教训

**所有 `StreamingResponse` 的 async generator 内部，都不应 `raise` 异常。** 因为 StreamingResponse 的 headers 在 generator 启动前就已发送，任何后续的异常抛出都无法通过 FastAPI 的全局异常处理器正常处理，必然导致 `RuntimeError: Caught handled exception, but response already started.` 和前端静默失败。

正确做法：一律通过 yield SSE 事件（如 `event: error`）传递错误信息。
