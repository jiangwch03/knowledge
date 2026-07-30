## Why

当前 `SessionContextMiddleware`、`@with_session`、`async_session_scope` / `session_scope` 会注入「无事务边界」的长生命周期 Session。首条 SQL 即隐式开事务并持锁到请求/任务结束；同时 `@transactional` 根事务又新建独立 Session，造成双 Session（脏读 / 看不到刚提交数据）与长事务冲突。需要在业务代码无侵入的前提下，让无 Service `@transactional` 时的 SQL 自动走短事务，并彻底取消非事务 Session 注入。

## What Changes

- **BREAKING**：移除全部非事务 Session 注入能力：`SessionContextMiddleware`、`@with_session` / `@with_session_sync`、`async_session_scope()` / `session_scope()`，以及对应的请求/任务级 Session 上下文。
- **BREAKING**：`get_current_session()` / `get_current_session_sync()` 仅从活跃 `@transactional` / `@transactional_sync` 栈获取 Session；无事务上下文时抛出 `TransactionException`（不再回退到请求/任务/代码块 Session）。
- 新增 `BaseDao`：子类在定义时通过 `__init_subclass__` 自动为公开异步/同步方法挂载 `@transactional()` / `@transactional_sync()`（`REQUIRED`），实现 DAO 隐式短事务；有外层事务时 join。
- `PageUtil.paginate` 同样挂载隐式短事务，语义与 DAO 一致。
- 迁移所有现有 `*Dao` 继承 `BaseDao`；清理调用方对 Middleware / `@with_session` / `*_session_scope` 的依赖，改为依赖 DAO 短事务或 Service 显式 `@transactional`。
- 不引入按方法名推断 `read_only`；读写分离不属于本变更范围。

## Capabilities

### New Capabilities

- `dao-implicit-short-transaction`：BaseDao 自动挂载隐式短事务，以及 `PageUtil.paginate` 隐式短事务的行为约定。

### Modified Capabilities

- `annotated-transaction`：删除非事务 Session 注入相关需求；收紧 `get_current_session` 仅事务上下文可用；更新与非 Web / 请求级 Session 相关的场景。

## Impact

- **核心模块**：`knowledge-common/.../transactional.py`、`middlewares/handle.py`、`utils/page_util.py`；新增 `BaseDao`（建议放在 `knowledge_common/mapper/dao` 或 `common`）。
- **全部 DAO**：约 30 个 `*Dao` 改为继承 `BaseDao`。
- **调用迁移**：HTTP 中间件注册；consumer / scheduler / agent tools / 部分 Service 上的 `@with_session`、`async_session_scope` / `session_scope`；直接 `get_current_session` 且无外层事务的 Service 代码需改为走 DAO 或加 `@transactional`。
- **文档与测试**：注解式事务文档、中间件链文档、`test_transactional.py` 及依赖 session scope 的测试需同步调整。
- **兼容性**：对依赖「请求级空挂 Session」的代码为破坏性变更；Service 多步写仍须显式 `@transactional`（DAO 各自短事务不自动合成原子边界）。
