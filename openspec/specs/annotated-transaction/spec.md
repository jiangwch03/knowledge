# 注解式事务管理

## Purpose

提供类 Spring `@Transactional` 的注解式事务管理功能，支持异步和同步双模式，实现代码无侵入式的事务控制。解决现有手动事务管理在复杂嵌套场景下的不足，支持事务传播行为、嵌套事务统一提交/回滚、以及非 Web 场景的 session 注入。

## Requirements

### Requirement: 异步注解式事务装饰器基础功能
系统必须提供一个 `@transactional` 装饰器，用于包装异步函数以实现事务管理。

#### Scenario: 异步事务成功提交
- **当** 一个被 `@transactional` 装饰的异步函数成功执行时
- **则** 事务应自动提交

#### Scenario: 异步事务异常时回滚
- **当** 一个被 `@transactional` 装饰的异步函数抛出异常时
- **则** 事务应自动回滚
- **并且** 原始异常应被重新抛出

### Requirement: 同步注解式事务装饰器基础功能
系统必须提供一个 `@transactional_sync` 装饰器，用于包装同步函数以实现事务管理。

#### Scenario: 同步事务成功提交
- **当** 一个被 `@transactional_sync` 装饰的同步函数成功执行时
- **则** 事务应自动提交

#### Scenario: 同步事务异常时回滚
- **当** 一个被 `@transactional_sync` 装饰的同步函数抛出异常时
- **则** 事务应自动回滚
- **并且** 原始异常应被重新抛出

### Requirement: 异步事务传播行为
系统必须支持类 Spring 的事务传播行为：REQUIRED、REQUIRES_NEW、SUPPORTS、NOT_SUPPORTED、NEVER、MANDATORY 和 NESTED。

#### Scenario: REQUIRED 且存在现有事务
- **当** 一个被 `@transactional(propagation=REQUIRED)` 装饰的方法在已有事务中被调用时
- **则** 它应加入现有事务

#### Scenario: REQUIRED 且不存在现有事务
- **当** 一个被 `@transactional(propagation=REQUIRED)` 装饰的方法在没有现有事务的情况下被调用时
- **则** 应创建一个新事务

#### Scenario: REQUIRES_NEW 挂起现有事务
- **当** 一个被 `@transactional(propagation=REQUIRES_NEW)` 装饰的方法在已有事务中被调用时
- **则** 现有事务应被挂起
- **并且** 应创建一个独立的新事务

#### Scenario: SUPPORTS 且存在现有事务
- **当** 一个被 `@transactional(propagation=SUPPORTS)` 装饰的方法在已有事务中被调用时
- **则** 它应加入现有事务

#### Scenario: SUPPORTS 且不存在现有事务
- **当** 一个被 `@transactional(propagation=SUPPORTS)` 装饰的方法在没有现有事务的情况下被调用时
- **则** 它应无事务运行

#### Scenario: NOT_SUPPORTED 挂起现有事务
- **当** 一个被 `@transactional(propagation=NOT_SUPPORTED)` 装饰的方法在已有事务中被调用时
- **则** 现有事务应被挂起
- **并且** 该方法应无事务运行

#### Scenario: NEVER 且存在现有事务
- **当** 一个被 `@transactional(propagation=NEVER)` 装饰的方法在已有事务中被调用时
- **则** 应抛出 TransactionException

#### Scenario: MANDATORY 且不存在现有事务
- **当** 一个被 `@transactional(propagation=MANDATORY)` 装饰的方法在没有现有事务的情况下被调用时
- **则** 应抛出 TransactionException

#### Scenario: NESTED 创建保存点
- **当** 一个被 `@transactional(propagation=NESTED)` 装饰的方法在已有事务中被调用时
- **则** 应创建一个保存点（savepoint）
- **并且** 在发生异常时，仅回滚到该保存点

### Requirement: 同步事务传播行为
系统必须支持类 Spring 的事务传播行为：REQUIRED、REQUIRES_NEW、SUPPORTS、NOT_SUPPORTED、NEVER、MANDATORY 和 NESTED。

#### Scenario: 同步 REQUIRED 且存在现有事务
- **当** 一个被 `@transactional_sync(propagation=REQUIRED)` 装饰的方法在已有同步事务中被调用时
- **则** 它应加入现有事务

#### Scenario: 同步 REQUIRED 且不存在现有事务
- **当** 一个被 `@transactional_sync(propagation=REQUIRED)` 装饰的方法在没有现有同步事务的情况下被调用时
- **则** 应创建一个新的同步事务

#### Scenario: 同步 REQUIRES_NEW 挂起现有事务
- **当** 一个被 `@transactional_sync(propagation=REQUIRES_NEW)` 装饰的方法在已有同步事务中被调用时
- **则** 现有事务应被挂起
- **并且** 应创建一个独立的新同步事务

#### Scenario: 同步 NESTED 创建保存点
- **当** 一个被 `@transactional_sync(propagation=NESTED)` 装饰的方法在已有同步事务中被调用时
- **则** 应创建一个保存点
- **并且** 在发生异常时，仅回滚到该保存点

### Requirement: 异步事务配置参数
系统必须支持在 `@transactional` 装饰器上配置 `isolation`、`read_only`、`timeout` 和 `rollback_for` 参数。

#### Scenario: 只读事务
- **当** 一个异步函数被 `@transactional(read_only=True)` 装饰时
- **则** 该事务应被标记为只读

#### Scenario: 自定义回滚异常
- **当** 一个异步函数被 `@transactional(rollback_for=[ValueError])` 装饰时
- **并且** 抛出了 `ValueError`
- **则** 事务应被回滚

#### Scenario: 特定异常不回滚
- **当** 一个异步函数被 `@transactional(no_rollback_for=[ValueError])` 装饰时
- **并且** 抛出了 `ValueError`
- **则** 事务不应被回滚

#### Scenario: 事务超时
- **当** 一个异步函数被 `@transactional(timeout=30)` 装饰时
- **并且** 函数执行超过 30 秒
- **则** 事务应自动回滚

### Requirement: 同步事务配置参数
系统必须支持在 `@transactional_sync` 装饰器上配置 `isolation`、`read_only`、`timeout` 和 `rollback_for` 参数。

#### Scenario: 同步只读事务
- **当** 一个同步函数被 `@transactional_sync(read_only=True)` 装饰时
- **则** 该事务应被标记为只读

#### Scenario: 同步自定义回滚异常
- **当** 一个同步函数被 `@transactional_sync(rollback_for=[ValueError])` 装饰时
- **并且** 抛出了 `ValueError`
- **则** 事务应被回滚

#### Scenario: 同步特定异常不回滚
- **当** 一个同步函数被 `@transactional_sync(no_rollback_for=[ValueError])` 装饰时
- **并且** 抛出了 `ValueError`
- **则** 事务不应被回滚

#### Scenario: 同步事务超时
- **当** 一个同步函数被 `@transactional_sync(timeout=30)` 装饰时
- **并且** 函数执行超过 30 秒
- **则** 事务应自动回滚

### Requirement: 异步嵌套事务统一提交和回滚
系统必须支持异步嵌套事务，即外层事务方法调用内层事务方法时，确保统一提交或回滚。

#### Scenario: 异步外层和内层事务均成功
- **当** 一个外层 `@transactional` 方法调用一个内层 `@transactional` 方法
- **并且** 两者均成功执行
- **则** 当最外层事务提交时，两者应一起被提交

#### Scenario: 异步内层事务失败
- **当** 一个外层 `@transactional` 方法调用一个内层 `@transactional` 方法
- **并且** 内层方法抛出异常
- **则** 整个事务（包括外层操作）应被回滚

### Requirement: 同步嵌套事务统一提交和回滚
系统必须支持同步嵌套事务，即外层同步事务方法调用内层同步事务方法时，确保统一提交或回滚。

#### Scenario: 同步外层和内层事务均成功
- **当** 一个外层 `@transactional_sync` 方法调用一个内层 `@transactional_sync` 方法
- **并且** 两者均成功执行
- **则** 当最外层事务提交时，两者应一起被提交

#### Scenario: 同步内层事务失败
- **当** 一个外层 `@transactional_sync` 方法调用一个内层 `@transactional_sync` 方法
- **并且** 内层方法抛出异常
- **则** 整个事务（包括外层操作）应被回滚

### Requirement: 异步事务上下文访问
系统必须提供 `get_current_session()` 函数，用于在异步事务方法内部获取当前事务的会话。

#### Scenario: 在异步事务内获取会话
- **当** `get_current_session()` 在 `@transactional` 装饰的方法内被调用时
- **则** 应返回当前的 AsyncSession

#### Scenario: 在请求上下文中获取会话（非事务场景）
- **当** `get_current_session()` 在 FastAPI 请求处理流程中被调用
- **并且** 当前请求已通过 SessionContextMiddleware 存入会话上下文
- **并且** 调用方不在 `@transactional` 装饰的方法内
- **则** 应返回当前请求对应的 AsyncSession

#### Scenario: 在非 Web 异步任务上下文中获取会话
- **当** `get_current_session()` 在 `@with_session` 装饰的后台任务方法中被调用
- **并且** 调用方不在 `@transactional` 装饰的方法内
- **则** 应返回当前任务对应的 AsyncSession

#### Scenario: 使用 async_session_scope 获取异步会话
- **当** `get_current_session()` 在 `async_session_scope()` 上下文管理器中被调用
- **并且** 调用方不在 `@transactional` 装饰的方法内
- **则** 应返回当前上下文对应的 AsyncSession

#### Scenario: 在异步事务外且无上下文时获取会话
- **当** `get_current_session()` 在任何 `@transactional` 装饰的方法外部被调用
- **并且** 也不在 FastAPI 请求处理流程中
- **并且** 也不在 `@with_session` 装饰的方法或 `async_session_scope()` 上下文中
- **则** 应抛出 TransactionException

### Requirement: 同步事务上下文访问
系统必须提供 `get_current_session_sync()` 函数，用于在同步事务方法内部获取当前事务的会话。

#### Scenario: 在同步事务内获取会话
- **当** `get_current_session_sync()` 在 `@transactional_sync` 装饰的方法内被调用时
- **则** 应返回当前的 Session

#### Scenario: 使用 session_scope 获取同步会话
- **当** `get_current_session_sync()` 在 `session_scope()` 上下文管理器中被调用
- **并且** 调用方不在 `@transactional_sync` 装饰的方法内
- **则** 应返回当前上下文对应的 Session

#### Scenario: 在同步事务外且无上下文时获取会话
- **当** `get_current_session_sync()` 在任何 `@transactional_sync` 装饰的方法外部被调用
- **并且** 也不在 `session_scope()` 上下文中
- **则** 应抛出 TransactionException

### Requirement: 非 Web 异步场景的会话注入
系统必须提供 `@with_session` 装饰器和 `async_session_scope()` 异步上下文管理器，用于在异步后台任务、异步定时任务、RPC 调用等非 Web 场景中注入会话上下文。

#### Scenario: 后台任务使用 with_session 装饰器
- **当** 一个后台任务方法被 `@with_session` 装饰
- **并且** 该方法被调用
- **则** 应自动创建 AsyncSession 并注入上下文
- **并且** 方法执行完毕后应自动关闭 session

#### Scenario: 定时任务使用 async_session_scope
- **当** 一段代码在 `async with async_session_scope():` 块中执行
- **则** 应自动创建 AsyncSession 并注入上下文
- **并且** 代码块退出时应自动关闭 session

#### Scenario: with_session 内调用 transactional
- **当** 一个 `@with_session` 装饰的方法调用 `@transactional` 装饰的方法
- **则** `@transactional` 应复用 `@with_session` 创建的 session
- **并且** 事务提交后 session 仍由 `@with_session` 负责关闭

### Requirement: 同步场景的会话注入
系统必须提供 `@with_session_sync` 装饰器和 `session_scope()` 同步上下文管理器，用于在同步定时任务、脚本执行等场景中注入会话上下文。

#### Scenario: 同步任务使用 with_session_sync 装饰器
- **当** 一个同步任务方法被 `@with_session_sync` 装饰
- **并且** 该方法被调用
- **则** 应自动创建 Session 并注入上下文
- **并且** 方法执行完毕后应自动关闭 session

#### Scenario: 同步脚本使用 session_scope
- **当** 一段代码在 `with session_scope():` 块中执行
- **则** 应自动创建 Session 并注入上下文
- **并且** 代码块退出时应自动关闭 session

#### Scenario: with_session_sync 内调用 transactional_sync
- **当** 一个 `@with_session_sync` 装饰的方法调用 `@transactional_sync` 装饰的方法
- **则** `@transactional_sync` 应复用 `@with_session_sync` 创建的 session
- **并且** 事务提交后 session 仍由 `@with_session_sync` 负责关闭

### Requirement: 向后兼容性
系统必须保持与现有手动事务管理代码的向后兼容性。

#### Scenario: 异步手动事务仍然有效
- **当** 现有代码继续使用手动的 `await query_db.commit()` 和 `await query_db.rollback()` 时
- **则** 它应在不修改的情况下继续正常工作

#### Scenario: 同步手动事务仍然有效
- **当** 现有代码继续使用手动的 `query_db.commit()` 和 `query_db.rollback()` 时
- **则** 它应在不修改的情况下继续正常工作
