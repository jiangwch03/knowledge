## 1. Core Transaction Management Infrastructure

- [x] 1.1 Create `knowledge_common/common/transactional.py` module with base types and enums (`PropagationBehavior`, `TransactionException`)
- [x] 1.2 Implement `AsyncTransactionContext` class using `ContextVar` to manage async transaction context stack per coroutine
- [x] 1.3 Implement `SyncTransactionContext` class using `threading.local()` to manage sync transaction context stack per thread
- [x] 1.4 Implement `_transactional` core decorator for async functions with AsyncSession lifecycle management
- [x] 1.5 Implement `_transactional_sync` core decorator for sync functions with Session lifecycle management

## 2. Async Transactional Decorator Implementation

- [x] 2.1 Implement `@transactional` decorator with `propagation` parameter supporting `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `NOT_SUPPORTED`, `NEVER`, `MANDATORY`, `NESTED`
- [x] 2.2 Implement async REQUIRED propagation: join existing transaction or create new one
- [x] 2.3 Implement async REQUIRES_NEW propagation: suspend current transaction and create independent new transaction
- [x] 2.4 Implement async SUPPORTS propagation: join if exists, otherwise run non-transactional
- [x] 2.5 Implement async NOT_SUPPORTED propagation: suspend current and run non-transactional
- [x] 2.6 Implement async NEVER propagation: raise TransactionException if transaction exists
- [x] 2.7 Implement async MANDATORY propagation: raise TransactionException if no transaction exists
- [x] 2.8 Implement async NESTED propagation: create savepoint within existing transaction

## 3. Sync Transactional Decorator Implementation

- [x] 3.1 Implement `@transactional_sync` decorator with `propagation` parameter supporting `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `NOT_SUPPORTED`, `NEVER`, `MANDATORY`, `NESTED`
- [x] 3.2 Implement sync REQUIRED propagation: join existing transaction or create new one
- [x] 3.3 Implement sync REQUIRES_NEW propagation: suspend current transaction and create independent new transaction
- [x] 3.4 Implement sync SUPPORTS propagation: join if exists, otherwise run non-transactional
- [x] 3.5 Implement sync NOT_SUPPORTED propagation: suspend current and run non-transactional
- [x] 3.6 Implement sync NEVER propagation: raise TransactionException if transaction exists
- [x] 3.7 Implement sync MANDATORY propagation: raise TransactionException if no transaction exists
- [x] 3.8 Implement sync NESTED propagation: create savepoint within existing transaction

## 4. Async Transaction Configuration and Parameters

- [x] 4.1 Implement `read_only` parameter support in `@transactional` decorator
- [x] 4.2 Implement `isolation` parameter support in `@transactional` decorator
- [x] 4.3 Implement `timeout` parameter support using asyncio.wait_for
- [x] 4.4 Implement `rollback_for` parameter in `@transactional` decorator
- [x] 4.5 Implement `no_rollback_for` parameter in `@transactional` decorator

## 5. Sync Transaction Configuration and Parameters

- [x] 5.1 Implement `read_only` parameter support in `@transactional_sync` decorator
- [x] 5.2 Implement `isolation` parameter support in `@transactional_sync` decorator
- [x] 5.3 Implement `timeout` parameter support using signal or threading.Timer
- [x] 5.4 Implement `rollback_for` parameter in `@transactional_sync` decorator
- [x] 5.5 Implement `no_rollback_for` parameter in `@transactional_sync` decorator

## 6. Async Session Access and DAO Integration

- [x] 6.1 Implement `get_current_session()` function with three-layer lookup: transaction context → request/task context → raise exception
- [x] 6.2 Implement `SessionContextMiddleware` FastAPI middleware to store `get_db()` session into ContextVar for non-transactional requests
- [x] 6.3 Implement `@with_session` decorator for non-Web async scenarios (background tasks, scheduled jobs, RPC calls)
- [x] 6.4 Implement `async_session_scope()` async context manager for non-Web async scenarios
- [x] 6.5 Ensure `get_current_session()` falls back to request/task-level session context when not inside a `@transactional` block
- [x] 6.6 Add transaction context awareness to a sample async DAO (DictDataDao, ConfigDao) to fetch session from context when not passed explicitly
- [x] 6.7 Update a sample async Service (ConfigService.add_config_services) to demonstrate `@transactional` usage without passing session parameters
- [ ] 6.8 Update a sample background task/scheduled job to demonstrate `@with_session` usage

## 7. Sync Session Access and DAO Integration

- [x] 7.1 Implement `get_current_session_sync()` function with two-layer lookup: transaction context → task context → raise exception
- [x] 7.2 Implement `@with_session_sync` decorator for sync scenarios (sync scheduled jobs, scripts)
- [x] 7.3 Implement `session_scope()` sync context manager for sync scenarios
- [x] 7.4 Add transaction context awareness to a sample sync DAO (JobLogDao) to fetch session from context when not passed explicitly
- [x] 7.5 Update a sample sync Service (JobLogService.add_job_log_services) to demonstrate `@transactional_sync` usage without passing session parameters
- [ ] 7.6 Update a sample sync scheduled job to demonstrate `@with_session_sync` usage

## 8. Async Testing

- [x] 8.1 Write unit tests for `AsyncTransactionContext` stack management (push, pop, current)
- [x] 8.2 Write unit tests for async REQUIRED propagation behavior
- [x] 8.3 Write unit tests for async REQUIRES_NEW propagation behavior
- [x] 8.4 Write unit tests for async NESTED propagation behavior (savepoint rollback)
- [x] 8.5 Write unit tests for async rollback_for and no_rollback_for configuration
- [x] 8.6 Write integration tests for async nested service calls with unified commit/rollback
- [x] 8.7 Write integration tests to verify async backward compatibility with existing manual transaction code

## 9. Sync Testing

- [x] 9.1 Write unit tests for `SyncTransactionContext` stack management (push, pop, current)
- [x] 9.2 Write unit tests for sync REQUIRED propagation behavior
- [x] 9.3 Write unit tests for sync REQUIRES_NEW propagation behavior
- [x] 9.4 Write unit tests for sync NESTED propagation behavior (savepoint rollback)
- [x] 9.5 Write unit tests for sync rollback_for and no_rollback_for configuration
- [x] 9.6 Write integration tests for sync nested service calls with unified commit/rollback
- [x] 9.7 Write integration tests to verify sync backward compatibility with existing manual transaction code

## 10. CI and Pipeline

- [x] 10.1 Add all transaction-related tests to CI pipeline (测试文件已创建，CI 配置沿用现有 pytest 配置)

## 11. Documentation and Migration

- [x] 11.1 Document `@transactional` and `@transactional_sync` decorator APIs and usage examples in module docstrings
- [x] 11.2 Create migration guide for converting existing manual async transaction code to `@transactional`
- [x] 11.3 Create migration guide for converting existing manual sync transaction code to `@transactional_sync`
- [x] 11.4 Update `knowledge-admin` service layer (ConfigService.add_config_services) to use `@transactional` as a pilot
- [x] 11.5 Update a sync service (JobLogService.add_job_log_services) to use `@transactional_sync` as a pilot
- [x] 11.6 Verify no regression in existing FastAPI dependency injection (`get_db`) behavior
