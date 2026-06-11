## Why

当前 Service 层写操作采用手动事务模式：接收 `query_db: AsyncSession` 参数，在方法体内 `try/except` 包裹 `await query_db.commit()` / `await query_db.rollback()`，Controller 层通过 `DBSessionDependency()` 注入 session 并逐层传递。这种模式导致：(1) 每个写方法重复 commit/rollback 样板代码；(2) 嵌套 Service 调用各自独立 session，无法统一事务；(3) Controller 被迫感知 DB session 并传递，耦合度高。项目已实现 `@transactional` 注解式事务装饰器（支持 7 种传播行为、自动 commit/rollback），但仅 `ConfigService.add_config_services` 一处试点使用，其余 40+ 个写方法仍为手动模式。

## What Changes

- **Service 层写操作方法**：添加 `@transactional()` 装饰器（装饰器自动 commit / 异常自动 rollback），移除手动 `try/commit/rollback` 样板代码，删除 `query_db` 参数，统一从 `get_current_session()` 获取 session。
- **Service 层读操作方法**：删除 `query_db` 参数，统一从 `get_current_session()` 获取 session。
- **DAO 层方法**：删除 `db: AsyncSession` 参数（不保留向后兼容），统一从 `get_current_session()` 获取 session。
- **Controller 层**：所有路由（读 + 写）移除 `query_db: Annotated[AsyncSession, DBSessionDependency()]` 注入，Service 调用不再传递 `query_db`。
- **涉及范围**：`knowledge-common`（config_service、dict_service、log_service、job_log_service）、`knowledge-admin`（user_service、role_service、dept_service、menu_service、post_service、job_service）及对应 DAO 和 Controller。

## Capabilities

### New Capabilities

（无新增 capability）

### Modified Capabilities

- `annotated-transaction`: 扩展 `@transactional` 的使用范围——从单点试点覆盖到全部 Service 层写操作，同时明确 Controller 层不再传递 session 的调用约定。

## Impact

- **核心代码**：`knowledge-common` 4 个 Service + 6 个 DAO 文件；`knowledge-admin` 6 个 Service + 9 个 DAO + 对应 Controller 文件。
- **改动模式**：机械性改造（删参数 → 加装饰器 → 删 try/commit/rollback），无新逻辑引入。
- **依赖**：无新增外部依赖，复用现有 `@transactional` + `get_current_session()` 基础设施。
- **兼容性**：不保留向后兼容——DAO 层 `db` 参数和 Service 层 `query_db` 参数直接删除，Controller 层 `DBSessionDependency` 全面移除。
