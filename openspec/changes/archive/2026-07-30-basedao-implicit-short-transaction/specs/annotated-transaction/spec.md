## MODIFIED Requirements

### Requirement: 异步事务上下文访问
系统必须提供 `get_current_session()` 函数，用于在异步事务方法内部获取当前事务的会话。`get_current_session()` MUST 仅从活跃的异步事务上下文栈获取 Session；MUST NOT 再从请求级、任务级或代码块级非事务 Session 上下文回退。

#### Scenario: 在异步事务内获取会话
- **当** `get_current_session()` 在 `@transactional` 装饰的方法内被调用时
- **则** 应返回当前的 AsyncSession

#### Scenario: 在 DAO 隐式短事务内获取会话
- **当** `get_current_session()` 在 `BaseDao` 子类已自动挂载事务的方法内被调用时
- **则** 应返回当前短事务或外层事务对应的 AsyncSession

#### Scenario: 在异步事务外获取会话
- **当** `get_current_session()` 在任何活跃异步事务上下文外部被调用时
- **则** 应抛出 TransactionException

### Requirement: 同步事务上下文访问
系统必须提供 `get_current_session_sync()` 函数，用于在同步事务方法内部获取当前事务的会话。`get_current_session_sync()` MUST 仅从活跃的同步事务上下文栈获取 Session；MUST NOT 再从任务级或代码块级非事务 Session 上下文回退。

#### Scenario: 在同步事务内获取会话
- **当** `get_current_session_sync()` 在 `@transactional_sync` 装饰的方法内被调用时
- **则** 应返回当前的 Session

#### Scenario: 在同步事务外获取会话
- **当** `get_current_session_sync()` 在任何活跃同步事务上下文外部被调用时
- **则** 应抛出 TransactionException

## REMOVED Requirements

### Requirement: 非 Web 异步场景的会话注入
**Reason**: 非事务 Session 注入会导致长事务持锁，并与 `@transactional` 新建 Session 形成双 Session。Session 改由事务边界（Service `@transactional` 或 DAO / PageUtil 隐式短事务）提供。
**Migration**: 删除 `@with_session` 与 `async_session_scope()`；后台任务、定时任务、consumer 改为直接调用 `BaseDao` 方法或带 `@transactional` 的 Service。原依赖注入 Session 的代码在无事务时改为进入 DAO/Service 事务边界后再访问 DB。

### Requirement: 同步场景的会话注入
**Reason**: 与异步侧相同，取消非事务 Session 注入以消除长事务与双 Session。
**Migration**: 删除 `@with_session_sync` 与 `session_scope()`；同步任务改为调用已挂载 `@transactional_sync` 的 DAO/Service，或为编排入口显式添加 `@transactional_sync`。
