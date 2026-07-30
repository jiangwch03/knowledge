## Context

项目已具备类 Spring 的 `@transactional` / `@transactional_sync`（含 7 种传播行为），DAO 统一通过 `get_current_session()` 取 Session。同时存在三套**非事务** Session 注入：

1. `SessionContextMiddleware`（HTTP 请求级）
2. `@with_session` / `@with_session_sync`（后台任务）
3. `async_session_scope()` / `session_scope()`（代码块）

问题：

- 非事务 Session 上首条 SQL 触发 SQLAlchemy autobegin，事务持有到请求/任务结束 → **长事务 / 持锁**。
- `@transactional` 根事务始终 `AsyncSessionLocal()` 新建 Session，与注入 Session 并存 → **双 Session**（可见性 / identity map 分裂）。

约束（已对齐）：

- 业务方法体无侵入（DAO 内仍 `get_current_session()`）。
- 无 Service `@transactional` 时，SQL 须自动短事务。
- **不复用、不保留**任何非事务 Session 注入。
- 不采用按方法名推断 `read_only`。
- 挂载方式采用 **BaseDao + `__init_subclass__`**。

## Goals / Non-Goals

**Goals:**

- Session 仅由事务边界提供；`get_current_session()` 只认事务栈。
- `BaseDao` 子类公开方法自动挂载 `REQUIRED` 短事务；外层有事务则 join。
- `PageUtil.paginate` 同样隐式短事务。
- 拆除 Middleware / `@with_session*` / `*_session_scope` 及请求/任务级上下文，并迁移全部调用方。

**Non-Goals:**

- 不实现 / 不强推 `read_only` 自动推断。
- 不在本变更内做读写分离路由。
- 不改变 `@transactional` 传播行为语义（REQUIRED / REQUIRES_NEW / NESTED 等保持现状）。
- 不强制给每个只读 Service 方法加 `@transactional`（由 DAO 短事务兜底）。
- 不解决「无 Service `@transactional` 时多 DAO 调用的跨方法原子性」——多步写仍须 Service 显式 `@transactional`。

## Decisions

### 1. 拆除全部非事务 Session，而非复用请求级 Session

- **选择**：删除 Middleware、`@with_session*`、`*_session_scope` 及 `_AsyncSessionContextManager` / `_SyncSessionContextManager`。
- **理由**：复用请求级 Session 仍会整请求占用连接，且与「短事务」目标纠缠；拆除后 Session 生命周期与事务边界严格一致，双 Session / 长事务从根消除。
- **备选**：根事务复用 Middleware Session（OSIV 风格）——已明确否决。

### 2. BaseDao + `__init_subclass__` 自动挂载

- **选择**：`BaseDao.__init_subclass__` 扫描子类 `__dict__`，对公开方法包装事务装饰器。
- **包装规则**：
  - 跳过以下划线 `_` 开头的属性。
  - `classmethod`：取出 `__func__` → 套装饰器 → 再 `classmethod(...)`。
  - `staticmethod`：同上。
  - 普通协程/函数：直接套装饰器。
  - 异步 → `@transactional()`；同步 → `@transactional_sync()`。
  - 已带事务装饰器的方法：跳过或幂等（避免双重包装）；实现时检测并跳过更稳妥。
- **理由**：比 metaclass 轻、比逐方法手写零侵入；「是 Dao」语义清晰，后续可挂通用能力。
- **备选**：类装饰器 `@dao_transactional`（工作量同级，不选）；metaclass（无额外收益，不选）。

### 3. PageUtil.paginate 单独挂隐式短事务

- **选择**：对 `paginate` 显式包一层 `@transactional()`（与 DAO 同语义）。
- **理由**：工具类不是 Dao，不继承 BaseDao；但会被 Service 直接调用，须自带事务边界。在已有外层事务（含 DAO 短事务）内调用时 `REQUIRED` join。

### 4. `@transactional` 根事务继续自建 Session（不复用外部）

- **选择**：`_run_in_async_transaction` 保持 `AsyncSessionLocal()` 新建；拆除注入后不存在「外部可复用 Session」。
- **理由**：与「不保留非事务 Session」一致；每个事务边界 = 一个 Session 生命周期。

### 5. 调用约定

- SQL 优先经 DAO；`PageUtil.paginate` 允许作为带事务边界的分页入口。
- Service 多步写必须 `@transactional`。
- 后台任务 / 定时任务 / consumer：去掉外层 `@with_session` / `async_session_scope`，直接调用 DAO 或带 `@transactional` 的 Service。
- Service 内直接 `get_current_session()` 且无外层事务：迁移为 DAO 调用或加 `@transactional`。

### 目标运行时序

```
无 Service @transactional                有 Service @transactional
─────────────────────────────            ─────────────────────────────
Dao.m1() → short TX1 commit              Service.write() begin (S)
Dao.m2() → short TX2 commit                Dao.m1 / m2 join S
PageUtil.paginate() → short TX commit    commit once
```

```
get_current_session()
  └─ 仅事务栈顶 session
  └─ 否则 TransactionException
```

## Risks / Trade-offs

- **[Risk] 漏继承 BaseDao → 方法无短事务，`get_current_session` 直接失败**  
  → Mitigation：全量 DAO 迁移列入 tasks；单测覆盖「无外层事务调用 BaseDao 子类方法可成功」；CI / 代码审查约定新 Dao 必须继承 BaseDao。

- **[Risk] 双重包装（方法已手写 `@transactional` 再被 BaseDao 包一层）**  
  → Mitigation：`_wrap_dao_methods` 检测已包装则跳过；或约定 DAO 方法不再手写事务装饰器。

- **[Risk] 无 Service 事务时多 DAO 各自 commit，破坏原「靠请求级 Session 凑合一起」的隐式原子性（若存在）**  
  → Mitigation：这是预期语义（类 Spring Data）；多步写必须显式 `@transactional`。迁移时审查原先依赖长 Session 的写路径。

- **[Risk] 调用方遗漏清理 `@with_session` / `async_session_scope`，或测试仍依赖旧 API**  
  → Mitigation：删除公开导出迫使编译/导入失败；按 grep 清单逐个迁移；更新 `test_transactional.py`。

- **[Trade-off] 每个 DAO 调用无外层事务时新建 Session** → 连接池 churn 高于「整请求一个 Session」，但换来短事务与无双 Session；可接受。

- **[Trade-off] 嵌套 DAO 调用在无外层 Service 事务时各自独立提交** → 与 Spring Data 默认一致；需要原子性时上提 Service `@transactional`。

## Migration Plan

1. 实现 `BaseDao` + `PageUtil.paginate` 隐式事务；收紧 `get_current_session*`；删除非事务注入 API（可分 PR：先加 BaseDao 并行，再拆注入）。
2. 全部 `*Dao` 改为 `class XxxDao(BaseDao)`。
3. 去掉 Middleware 注册；迁移 `@with_session` / `*_session_scope` 调用点；清理 Service 直取 session 遗留。
4. 更新单元测试与基础设施文档。
5. 回滚策略：若生产异常，可临时恢复 Middleware（不推荐长期）；更稳妥是按模块 feature 开关难以做到——建议在预发充分回归读列表、写多步、后台 consumer / scheduler。

## Open Questions

- 无（关键决策已收敛）。实现期若发现个别 DAO 方法不宜自动事务（极罕见），可再约定逃逸机制（如命名前缀或显式标记跳过），当前不预留。
