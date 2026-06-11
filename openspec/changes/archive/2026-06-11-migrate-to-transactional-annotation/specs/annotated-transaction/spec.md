## ADDED Requirements

### Requirement: Service 层写操作方法必须使用 @transactional 装饰器
所有 Service 层执行数据库写操作（INSERT / UPDATE / DELETE）的方法必须使用 `@transactional()` 装饰器声明事务边界。装饰器负责自动 commit（方法正常返回时）和自动 rollback（方法抛出异常时），禁止手动调用 `await db.commit()` / `await db.rollback()`。

#### Scenario: 写操作方法使用 @transactional 装饰器
- **WHEN** 一个 Service 方法包含数据库写操作
- **THEN** 该方法必须被 `@transactional()` 装饰
- **AND** 方法体内不得出现 `await db.commit()` 或 `await db.rollback()`

#### Scenario: @transactional 方法正常返回时自动 commit
- **WHEN** 一个 `@transactional()` 装饰的方法正常返回（未抛出异常）
- **THEN** 装饰器必须自动 commit 当前事务

#### Scenario: @transactional 方法抛出异常时自动 rollback
- **WHEN** 一个 `@transactional()` 装饰的方法抛出异常
- **THEN** 装饰器必须自动 rollback 当前事务
- **AND** 原始异常必须被重新抛出

#### Scenario: @transactional 方法内嵌套调用其他 @transactional 方法
- **WHEN** 一个 `@transactional` 方法调用另一个 `@transactional` 方法
- **THEN** 内层方法必须通过 REQUIRED 传播行为加入外层事务
- **AND** 两者共享同一 session，由最外层统一 commit / rollback

### Requirement: Service 层方法删除 query_db 参数
Service 层方法必须删除 `query_db: AsyncSession` 参数。方法内部统一通过 `get_current_session()` 从上下文获取 session。

#### Scenario: Service 方法通过 get_current_session() 获取 session
- **WHEN** Service 方法需要操作数据库
- **THEN** 方法内部必须调用 `get_current_session()` 获取 session
- **AND** 在 `@transactional` 上下文中必须能正常获取到事务 session

### Requirement: DAO 层方法删除 db 参数
DAO 层方法必须删除 `db: AsyncSession` 参数。方法内部统一通过 `get_current_session()` 从上下文获取 session。不保留向后兼容。

#### Scenario: DAO 方法通过 get_current_session() 获取 session
- **WHEN** DAO 方法需要操作数据库
- **THEN** 方法内部必须调用 `get_current_session()` 获取 session
- **AND** 方法签名中不得包含 `db` 参数

### Requirement: Controller 层全面移除 DBSessionDependency
Controller 层所有路由（读 + 写）不得通过 `DBSessionDependency()` 注入 `query_db`，调用 Service 时不传递 session 参数。

#### Scenario: Controller 路由不注入 session
- **WHEN** 一个 Controller route handler 被调用
- **THEN** 该 handler 不得声明 `query_db: Annotated[AsyncSession, DBSessionDependency()]` 参数
- **AND** 调用 Service 方法时不传递 `query_db`
