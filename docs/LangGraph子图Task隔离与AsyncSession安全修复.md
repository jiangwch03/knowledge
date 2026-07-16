# LangGraph 子图 Task 隔离与 AsyncSession 安全修复

## 问题描述

生产环境出现 `asyncmy.errors.OperationalError: (2014, 'Command Out of Sync')` 错误，发生在 LangGraph 爬虫 Agent 的 `astream(subgraphs=True)` 执行流程中。

## 根因分析

### 核心原因：AsyncSession 跨 asyncio Task 共享

SQLAlchemy `AsyncSession` 是 **asyncio Task-safe**（单 Task 内安全），但不是 **cross-Task-safe**（不能跨 Task 共享）。

LangGraph 的 `astream(subgraphs=True)` 在内部通过 `asyncio.create_task` 创建新的 asyncio Task 来执行子图。Python 的 `contextvars.ContextVar` 在 `create_task` 时会自动将当前 Task 的所有 ContextVar 值复制到子 Task（`copy_context` 机制）。

项目的 session 上下文通过 `contextvars.ContextVar` 在 `_AsyncSessionContextManager` 中存储。这意味着：

1. 父 Task（FastAPI 请求协程）持有中间件注入的 `AsyncSession`
2. LangGraph 创建子图 Task 时，子 Task 通过 ContextVar 继承拿到了**同一个** `AsyncSession` 对象
3. 子图内 `analyze_node` → `get_llm_with_tools` → `_get_model_config` → `AiModelFunctionAdapterDao.get_adapter_by_param_id` 使用该 session 执行 SQL
4. 当 `_finalize_fairy`（连接池回收回调）在错误的 Task/绿色上下文链中执行时，asyncmy 的 `_read_ok_packet()` 检测到 MySQL 协议状态不匹配，抛出 `Command Out of Sync`

### 关键代码路径

```
chat_stream（父 Task）
  └─ compiled.astream(subgraphs=True)
       └─ LangGraph 内部 create_task（子 Task B）
            └─ analyze_node
                 └─ get_llm_with_tools
                      └─ _get_model_config
                           └─ get_current_session() → 拿到父 Task 的 session
                           └─ db.execute() → Command Out of Sync ✗
```

### 错误认知排除

- ❌ 不是 SQL 并发执行导致（同一时间点只有一个 SQL）
- ❌ 不是数据库连接池耗尽
- ✅ 是跨 Task 共享 `AsyncSession` 导致 greenlet 上下文链断裂，asyncmy 协议状态错乱

## 修复方案

### 方案演变

| 方案 | 描述 | 问题 |
|------|------|------|
| 永久缓存 | 永久缓存模型配置，绕过子图 DB 访问 | 模型配置可能变动，不灵活 |
| `@with_session` 手动隔离 | 子图节点使用 `@with_session` | 受上层 `@transactional` 事务栈影响，同 Task 嵌套场景有冲突 |
| **`ContextVarTaskLocal`** ✅ | 自定义 Task 级存储，不参与 `copy_context` | 根治，零副作用 |

### 最终方案：ContextVarTaskLocal

创建 `ContextVarTaskLocal` 类，替代 `contextvars.ContextVar` 用于 session 上下文存储。

**原理**：`asyncio.create_task` 的 `copy_context` 只会复制 **原生 `contextvars.ContextVar`** 对象。自定义类 `ContextVarTaskLocal` 使用 `asyncio.current_task().id()` 作为 key 进行 Task 级隔离存储，不被 `copy_context` 识别，自然不会被继承。

```python
class ContextVarTaskLocal(Generic[_T]):
    """按 asyncio.Task ID 隔离存储，子 Task 不会继承父 Task 的值"""

    def get(self) -> _T:
        task = asyncio.current_task()
        if task is None:
            return self._default
        return self._storage.get(id(task), self._default)

    def set(self, value: _T) -> None:
        task = asyncio.current_task()
        self._storage[id(task)] = value
```

### 改动范围

只改了 `_AsyncSessionContextManager` 的存储后端，其他代码零改动：

```python
# 修改前
class _AsyncSessionContextManager:
    _ctx_var: contextvars.ContextVar[...] = contextvars.ContextVar(...)

# 修改后
class _AsyncSessionContextManager:
    _ctx_var: ContextVarTaskLocal[...] = ContextVarTaskLocal(...)
```

事务栈（`_AsyncTransactionContextManager`）保持原生 `ContextVar` 不变，因为 `@transactional` 的 push/pop 在同 Task 内需要原生 ContextVar 的正常行为。

### 文件结构

- `knowledge-common/src/knowledge_common/common/context_var_task_local.py` — `ContextVarTaskLocal` 公共工具类
- `knowledge-common/src/knowledge_common/common/transactional.py` — 替换 `_AsyncSessionContextManager._ctx_var` 存储后端

### 效果验证

- 子图 Task：`ContextVarTaskLocal.get()` → `None`（不继承）→ `@with_session` 创建独立 session
- 同 Task：行为完全不变，`@transactional` / `@with_session` / 中间件均正常工作
- 测试：156 passed + 流式子图测试全部通过

## 核心概念澄清

| 概念 | 说明 |
|------|------|
| 事件循环（Event Loop） | 每个进程一个，单线程调度器 |
| asyncio Task | 事件循环内的执行单元，`create_task` 创建 |
| 协程（Coroutine） | Task 内的具体执行步骤，`await` 切换 |
| `contextvars.ContextVar` | 原生实现，`create_task` 时自动复制快照到子 Task |
| `ContextVarTaskLocal` | 自定义实现，Task ID 隔离，不参与 `copy_context` |
| `AsyncSession` **Task-safe** | 同一个 Task 内多个 `await` 安全 |
| `AsyncSession` **cross-Task-safe** | 不可跨 Task 共享，否则 greenlet 上下文链断裂 |
