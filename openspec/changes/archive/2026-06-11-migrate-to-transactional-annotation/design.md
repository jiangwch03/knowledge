## Context

项目已实现完整的 `@transactional` 注解式事务机制（`transactional.py`），支持 7 种传播行为、自动 commit/rollback、嵌套事务统一提交。但当前仅 `ConfigService.add_config_services` 一处试点使用，其余 40+ 个 Service 写方法仍采用手动 `try/commit/rollback` 模式。

当前调用链：
```
Controller (DBSessionDependency → query_db)
  → Service (query_db: AsyncSession, try/commit/rollback)
    → DAO (db: AsyncSession 必传)
```

目标调用链：
```
Controller (无 db 相关参数)
  → Service (@transactional 自动 commit，异常自动 rollback)
    → DAO (无 db 参数，统一 get_current_session())
```

## Goals / Non-Goals

**Goals:**

- 全部 Service 写操作方法加 `@transactional()` 装饰器，由装饰器自动 commit / 异常时自动 rollback，移除手动 `try/commit/rollback` 样板代码
- Service 层所有方法删除 `query_db` 参数，统一从 `get_current_session()` 获取 session
- DAO 层所有方法删除 `db` 参数，统一从 `get_current_session()` 获取 session（不保留向后兼容）
- Controller 层所有路由删除 `DBSessionDependency()` 注入及相关 db 参数，调用 Service 不传 session

**Non-Goals:**

- 不修改 `@transactional` / `@transactional_sync` 装饰器本身的实现
- 不修改 `SessionContextMiddleware`、`@with_session`、`async_session_scope` 等非事务 session 注入机制
- 不处理 DB + Redis 混合操作的严格一致性（保持最终一致性，与现有行为一致）

## Decisions

### Decision 1: Controller 层全面移除 DBSessionDependency

**选择**：所有路由（读 + 写）不再注入 `query_db`，Service 调用不传 session。

**理由**：
- `@transactional` 装饰器内部自行创建 session 并管理事务，无需外部注入
- 读操作同样通过 `get_current_session()` 获取 session，无需 Controller 传递
- 统一规则：Controller 不感知 db，消除读写路由的差异困惑

### Decision 2: DAO 层删除 db 参数，不保留向后兼容

**选择**：DAO 方法签名中直接删除 `db` 参数，方法体统一使用 `get_current_session()` 获取 session。

**理由**：
- 不保留 `db: AsyncSession | None = None` 的兼容形态，避免两种调用方式并存造成混乱
- 改造一步到位，DAO 接口更简洁——调用方无需关心 session 从哪来
- 与 `@transactional` 的 session 上下文栈无缝对接

### Decision 3: 按模块逐文件改造，每个文件独立可验证

**选择**：改造顺序为 DAO → Service → Controller，按模块（config、dict、post、role...）逐文件推进。

**理由**：
- DAO 先改（删 db 参数），Service 再改（删 query_db 参数 + 加装饰器），Controller 最后改（移除注入）
- 每个文件改造完即可独立验证编译通过，无需等全部改完
- 出问题时可精确定位到具体文件

## Risks / Trade-offs

### Risk 1: 改造量大，涉及文件多

- **风险**：40+ 个 Service 方法 + 对应 DAO + Controller，改造过程可能遗漏
- **缓解**：按模块逐文件推进，每个文件改造后验证编译；改造模式完全机械化（删参数 → 加装饰器 → 删 try/commit），无逻辑变更

### Risk 2: 嵌套 Service 调用的事务传播

- **风险**：外层 `@transactional` 调用内层也带 `@transactional` 的方法时，需确保传播行为正确
- **缓解**：默认 REQUIRED 传播行为——内层检测到活跃事务则直接加入，不会新建事务。嵌套事务统一由最外层 commit/rollback
