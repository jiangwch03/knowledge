# StreamingResponse 异常静默失败

## 背景

爬虫对话「确认 / resume」后前端无任何提示、也无输出；后端日志出现：

`RuntimeError: Caught handled exception, but response already started.`

## 原因

`StreamingResponse` 会**先发 HTTP 200 头**，再跑 async generator。generator 里若 `raise ServiceException`：

1. 全局异常处理器想改成错误 JSON 响应
2. 响应已开始，Starlette 拒绝修改 → 抛上述 RuntimeError
3. 前端已收到 200，SSE body 被截断且无合法事件 → 解析静默跳过，表现为完全无反馈

## 修复

流式 generator **不要 raise**，改为 `yield` SSE `error` 事件（前端已处理该事件并弹窗）：

```python
# ❌ headers 已发出后再 raise → 静默失败
raise ServiceException(...)

# ✅
yield _format_sse('error', {'message': error_msg})
return
```

并加全局 `try/except`，意外异常同样 yield `error`。

实现：`knowledge_content/agents/service/crawler_agent_service.py`（`resume_stream` / `chat_stream`）。
