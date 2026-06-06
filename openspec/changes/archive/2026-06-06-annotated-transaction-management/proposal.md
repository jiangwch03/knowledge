## Why

当前项目中，事务管理完全依赖 FastAPI 的依赖注入 session 进行代码层面的事务控制。这种方式在简单场景下尚可工作，但面对复杂事务场景（如事务方法 A 调用事务方法 B）时，两个事务上下文无法做到统一提交和回滚，极易导致数据不一致问题。此外，现有方式对业务代码侵入性较强，缺乏灵活性和可扩展性。因此，我们需要引入一套类似 Spring `@Transactional` 注解的事务管理机制，以实现对代码零侵入、灵活可控的事务管理。

## What Changes

- 在 `knowledge-common` 中新增注解式事务管理基础设施（transactional 装饰器、事务传播行为、事务上下文栈）
- 实现类似 Spring 的 `@Transactional` 注解装饰器，支持 `propagation`、`isolation`、`read_only`、`timeout`、`rollback_for` 等参数
- 实现事务上下文栈管理，支持嵌套事务和统一提交/回滚
- 提供事务传播行为支持：`REQUIRED`、`REQUIRES_NEW`、`SUPPORTS`、`NOT_SUPPORTED`、`NEVER`、`MANDATORY`、`NESTED`
- 在现有业务代码中引入无侵入式的事务管理替换原有的手动 session 事务控制

## Capabilities

### New Capabilities
- `annotated-transaction`: 注解式事务管理基础设施，提供类 Spring 的 `@Transactional` 装饰器、事务传播行为控制、嵌套事务统一提交/回滚能力

### Modified Capabilities
<!-- 无现有 spec 需要修改 -->

## Impact

- **代码范围**: 主要影响 `knowledge-common` 公共基础包（新增事务管理模块），以及 `knowledge-admin` 等业务模块（逐步替换手动事务控制）
- **API 变更**: 新增装饰器 API，对现有 API 无破坏性变更
- **依赖影响**: 需确保 SQLAlchemy 2.0 的 session 管理机制与事务管理器兼容
- **测试影响**: 需补充事务管理相关的单元测试和集成测试
