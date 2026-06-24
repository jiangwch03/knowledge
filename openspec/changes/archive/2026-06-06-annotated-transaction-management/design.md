## Context

当前项目基于 FastAPI + SQLAlchemy 2.0（AsyncSession）构建，事务管理采用最基础的手动模式：在每个 Service 方法中通过 try-except 包裹 `await query_db.commit()` 和 `await query_db.rollback()`。Controller 层通过 FastAPI 依赖注入 `get_db()` 获取 AsyncSession，再逐层传递到 Service 和 DAO。

这种模式存在以下问题：
1. **侵入性强**：每个需要事务的方法都必须显式写 commit/rollback，重复代码多
2. **嵌套事务无法统一管理**：Service A（事务方法）调用 Service B（事务方法）时，两者使用独立的 session，无法做到统一提交/回滚
3. **传播行为缺失**：无法根据业务需求灵活控制事务边界（如 REQUIRES_NEW、NESTED 等）
4. **可读性差**：业务逻辑被事务控制代码干扰

## Goals / Non-Goals

**Goals:**
- 实现类 Spring `@Transactional` 的注解式事务管理装饰器，对业务代码零侵入
- 同时支持 **异步**（AsyncSession）和 **同步**（Session）两种 session 模式
- 支持事务传播行为（REQUIRED、REQUIRES_NEW、SUPPORTS、NOT_SUPPORTED、NEVER、MANDATORY、NESTED）
- 支持嵌套事务场景下的事务统一提交和回滚
- 提供事务隔离级别、只读、超时、回滚异常类型等参数配置
- 向后兼容现有手动事务模式，支持平滑迁移

**Non-Goals:**
- 不替换 SQLAlchemy 的底层事务机制，而是基于其 session 事务能力进行封装
- 不支持分布式事务（如两阶段提交、Saga 等）
- 本次不强制替换所有现有手动事务代码（提供逐步迁移路径）

## Decisions

### 1. 基于 ContextVar + threading.local 实现双模式事务上下文栈
**决策**：异步场景使用 `contextvars.ContextVar` 维护事务上下文栈；同步场景使用 `threading.local()` 维护事务上下文栈。两套上下文相互独立，API 对称。

**理由**：
- `ContextVar` 天然支持 asyncio 的并发隔离，每个协程拥有独立的事务上下文
- `threading.local()` 天然支持同步代码的线程隔离
- 避免全局变量在多请求/多线程并发时的竞态条件问题
- 异步和同步场景分离，避免在同一个模块中混用两种上下文机制导致复杂度爆炸

**替代方案**：全局字典 + request_id → 复杂度高且容易出错；单一 ContextVar 覆盖同步场景 → 在纯同步线程池中行为不一致

### 2. 装饰器 + 上下文栈实现传播行为
**决策**：`@transactional` 装饰器内部维护一个 `TransactionContext` 栈，根据传播行为决定复用、新建或挂起事务。

**理由**：
- 装饰器模式是 Python 中最接近 Spring AOP 的实现方式
- 通过栈结构可以清晰追踪嵌套事务层级
- 顶层事务负责最终的 commit/rollback，嵌套事务通过 savepoint 管理

**传播行为实现策略**：
- `REQUIRED`（默认）：如果栈顶有活跃事务，复用；否则新建
- `REQUIRES_NEW`：新建事务上下文，挂起当前事务（入栈），方法结束后恢复
- `SUPPORTS`：如果有事务则加入，否则无事务运行
- `NOT_SUPPORTED`：挂起当前事务，无事务运行
- `NEVER`：无事务运行，如果存在事务则抛出异常
- `MANDATORY`：必须有事务，否则抛出异常
- `NESTED`：在当前事务中创建 savepoint，回滚时只回滚到 savepoint

### 3. session 的自动注入与管理（异步 + 同步双模式）
**决策**：事务管理器内部根据被装饰函数的类型自动选择 session 工厂：异步函数使用 `AsyncSessionLocal()`，同步函数使用 `SessionLocal()`。两种模式各自独立管理生命周期。

**理由**：
- 实现真正的无侵入式事务管理，Service 方法不再需要接收 `query_db: AsyncSession` 参数
- 嵌套调用时，内层方法可以通过 `get_current_session()` 获取当前事务 session，实现统一事务
- 但这也意味着需要修改 DAO 层，使其支持从上下文获取 session

**同步场景说明**：
- 项目中存在少量同步 session 的使用（如 `job_log_service.py` 中的同步日志写入）
- 同步版本使用 `@transactional_sync` 装饰器和 `get_current_session_sync()` API，与异步版本对称
- 同步版本不支持 FastAPI 中间件注入（FastAPI 本身是基于 async 的），但支持 `@with_session_sync` 装饰器和 `session_scope()` 上下文管理器

**替代方案**：继续传递 session 参数 → 无法实现真正的无侵入式，且嵌套调用问题依然存在

### 4. 回滚异常配置策略
**决策**：默认在捕获到任何 `Exception` 时回滚，支持通过 `rollback_for` 参数指定特定异常类型才回滚，`no_rollback_for` 参数指定不触发回滚的异常。

**理由**：
- 与 Spring 的 `@Transactional` 行为一致，降低学习成本
- 默认全部回滚是最安全的策略

### 5. 向后兼容与平滑迁移
**决策**：新的事务管理机制与现有手动事务模式共存，不强制替换。

**理由**：
- 避免一次性大规模重构带来的风险
- 现有代码继续使用 `query_db: AsyncSession` + 手动 commit/rollback
- 新功能或重构时逐步迁移到 `@transactional` 模式

### 6. 双通道 session 上下文：FastAPI 中间件 + 非 Web 场景上下文管理器
**决策**：为 `get_current_session()`（异步）和 `get_current_session_sync()`（同步）提供双通道 session 注入机制：
1. **FastAPI 请求场景**：通过 `SessionContextMiddleware` 中间件，在请求进入时将 `get_db()` 创建的 AsyncSession 存入 `ContextVar`
2. **非 Web 异步场景**（后台任务、定时任务、RPC 调用）：提供 `@with_session` 装饰器和 `async_session_scope()` 异步上下文管理器
3. **同步场景**（同步定时任务、脚本执行）：提供 `@with_session_sync` 装饰器和 `session_scope()` 同步上下文管理器

**理由**：
- 大量只读查询场景不需要事务，但仍需获取 session 执行查询
- `get_db()` 已经通过依赖注入为每个请求创建了 session，无需额外创建
- 中间件机制与 FastAPI 的请求生命周期天然契合，请求结束时自动关闭 session
- 后台任务/定时任务/RPC 调用不在 HTTP 请求生命周期内，无法使用 FastAPI 依赖注入，需要独立的 session 注入机制
- `@with_session` 语法糖使非 Web 场景也能享受无侵入式 session 管理
- 为 `@transactional` 的逐步推广提供支撑：DAO 层统一从上下文获取 session，无需关心调用方是在 Web 请求中、后台任务中，还是使用了 `@transactional`

**工作机制**：
- **FastAPI 异步场景**：请求到达时，中间件调用 `get_db()` 获取 AsyncSession，通过 `session_context.set(session)` 存入 ContextVar；请求结束后清理
- **非 Web 异步场景**：`@with_session` 装饰器或 `async_session_scope()` 内部通过 `AsyncSessionLocal()` 创建 session，存入 `session_context`
- **同步场景**：`@with_session_sync` 装饰器或 `session_scope()` 内部通过 `SessionLocal()` 创建 session，存入 `threading.local()`
- `get_current_session()`（异步）查找优先级：事务上下文 → 请求/任务级上下文 → 抛出异常
- `get_current_session_sync()`（同步）查找优先级：事务上下文 → 任务级上下文 → 抛出异常

## Risks / Trade-offs

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 异步上下文切换导致事务上下文丢失 | 高 | 确保所有异步操作（如 `await`）在事务上下文内部执行；`ContextVar` 会自动传播到子协程 |
| 与 FastAPI 依赖注入的 session 冲突 | 中 | 提供过渡方案：允许同时存在；文档明确说明使用 `@transactional` 时不需要注入 session |
| 嵌套事务层级过深导致性能下降 | 低 | savepoint 的开销通常很小；NESTED 传播行为按需使用 |
| 事务超时实现复杂度 | 低 | 使用 asyncio.wait_for 实现超时控制；默认不设置超时 |

## Migration Plan

**迁移步骤**：
1. **阶段一**：在 `knowledge-common` 中新增事务管理模块（`transactional.py`），实现核心 `@transactional` 装饰器和事务上下文
2. **阶段二**：选择一个简单的 Service 层（如 DictService）作为试点，验证事务管理功能
3. **阶段三**：逐步在 `knowledge-admin` 和 `knowledge-content` 中推广使用
4. **阶段四**：编写事务管理相关的单元测试和集成测试，确保覆盖率

**回滚策略**：
- 如发现重大问题，可立即停止使用 `@transactional` 装饰器，回退到手动事务模式
- 不涉及数据库 schema 变更，回滚成本低

## Open Questions

1. ~~DAO 层如何获取 session~~ ✅ **已解决**：`get_current_session()` 统一从三层上下文中获取：事务上下文（`@transactional` 内）→ 请求/任务级上下文（FastAPI 中间件或 `@with_session` 内）→ 抛出异常
2. ~~同步 session 支持~~ ✅ **已解决**：同步和异步同时实现，提供对称的 API：`@transactional_sync` / `get_current_session_sync()` / `@with_session_sync` / `session_scope()`
3. **事务日志和监控**：是否需要记录事务的开始、提交、回滚等事件用于监控？
   - **暂定方案**：预留接口，默认不开启，后续根据运维需求扩展
