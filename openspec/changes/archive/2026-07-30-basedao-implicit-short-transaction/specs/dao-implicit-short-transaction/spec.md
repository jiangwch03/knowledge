## ADDED Requirements

### Requirement: BaseDao 自动挂载隐式短事务
系统 MUST 提供 `BaseDao` 基类。凡继承 `BaseDao` 的子类，在类定义完成时 MUST 通过 `__init_subclass__` 为其公开方法自动挂载事务装饰器，使得业务方法体无需手写 `@transactional` / `@transactional_sync` 即可获得事务边界。

自动挂载规则 MUST 满足：
- 跳过名称以下划线 `_` 开头的属性
- 对 `classmethod` / `staticmethod`：先包装底层函数，再恢复为原 descriptor 类型
- 异步可调用对象挂载 `@transactional()`（默认 `propagation=REQUIRED`）
- 同步可调用对象挂载 `@transactional_sync()`（默认 `propagation=REQUIRED`）
- 已具备事务装饰行为的方法 MUST NOT 被重复包装

#### Scenario: 无外层事务时 DAO 方法自动开启短事务
- **WHEN** 调用 `BaseDao` 子类的公开异步方法
- **AND** 当前不存在活跃的异步事务上下文
- **THEN** 系统 MUST 为该次调用新建 AsyncSession 与事务
- **AND** 方法正常返回时 MUST 提交并关闭该 Session
- **AND** 方法内 `get_current_session()` MUST 返回该事务 Session

#### Scenario: 有外层事务时 DAO 方法加入现有事务
- **WHEN** 在 `@transactional` 装饰的 Service 方法内调用 `BaseDao` 子类公开方法
- **THEN** 该 DAO 方法 MUST 加入外层事务（不新建独立根事务）
- **AND** MUST NOT 在 DAO 方法返回时单独提交外层事务

#### Scenario: DAO 方法异常时短事务回滚
- **WHEN** 无外层事务时调用 `BaseDao` 子类公开方法
- **AND** 该方法抛出异常
- **THEN** 系统 MUST 回滚该短事务
- **AND** MUST 重新抛出原始异常

#### Scenario: classmethod 与 staticmethod 均可被挂载
- **WHEN** `BaseDao` 子类以 `@classmethod` 或 `@staticmethod` 定义公开异步方法
- **THEN** 自动挂载后通过 `XxxDao.method(...)` 调用 MUST 仍具备隐式短事务语义
- **AND** 调用约定 MUST 与挂载前一致（无需实例化）

#### Scenario: 私有方法不被自动挂载
- **WHEN** `BaseDao` 子类定义名称以 `_` 开头的方法
- **THEN** 系统 MUST NOT 为其自动挂载事务装饰器

### Requirement: PageUtil.paginate 隐式短事务
系统 MUST 为 `PageUtil.paginate` 提供与 DAO 隐式短事务相同的事务边界：默认 `propagation=REQUIRED` 的异步事务包装。

#### Scenario: 无外层事务时 paginate 自开短事务
- **WHEN** 在无活跃异步事务上下文中调用 `PageUtil.paginate`
- **THEN** 系统 MUST 新建短事务并在其中执行分页查询
- **AND** 正常返回时 MUST 提交该短事务

#### Scenario: 有外层事务时 paginate 加入现有事务
- **WHEN** 在 `@transactional` 或 DAO 隐式短事务内调用 `PageUtil.paginate`
- **THEN** `paginate` MUST 加入当前事务
- **AND** MUST NOT 在返回时单独提交外层事务

### Requirement: 新 DAO 必须继承 BaseDao
项目内所有持久化 DAO 类 MUST 继承 `BaseDao`，以便获得隐式短事务能力。

#### Scenario: 现有 Dao 完成基类迁移
- **WHEN** 变更落地完成
- **THEN** 仓库中既有的 `*Dao` 持久化类 MUST 均继承 `BaseDao`
