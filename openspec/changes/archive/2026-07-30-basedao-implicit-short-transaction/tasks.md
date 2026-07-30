## 1. 核心基础设施

- [x] 1.1 新增 `BaseDao`（含 `__init_subclass__` + `_wrap_dao_methods`）：公开 classmethod/staticmethod/协程方法自动挂载 `@transactional` / `@transactional_sync`，跳过 `_` 前缀与已包装方法
- [x] 1.2 为 `PageUtil.paginate` 挂载 `@transactional()`（REQUIRED），保证无外层事务时自开短事务、有外层时 join
- [x] 1.3 收紧 `get_current_session()` / `get_current_session_sync()`：仅从事务栈获取；删除对请求/任务级 Session 上下文的回退
- [x] 1.4 从 `transactional.py` 与 `knowledge_common.common` 公开 API 中移除 `SessionContextMiddleware`、`with_session`、`with_session_sync`、`async_session_scope`、`session_scope` 及内部 Session 上下文管理器
- [x] 1.5 从 `middlewares/handle.py` 取消注册 `SessionContextMiddleware`

## 2. DAO 迁移

- [x] 2.1 将 `knowledge-common` 下全部 `*Dao` 改为继承 `BaseDao`
- [x] 2.2 将 `knowledge-admin` 下全部 `*Dao` 改为继承 `BaseDao`
- [x] 2.3 将 `knowledge-content` 下全部 `*Dao` 改为继承 `BaseDao`
- [x] 2.4 将 `knowledge-retrieval` 下全部 `*Dao` 改为继承 `BaseDao`

## 3. 调用方迁移（拆除非事务 Session）

- [x] 3.1 迁移 HTTP/中间件相关引用与文档中的 Middleware 依赖
- [x] 3.2 迁移 message consumer 上的 `@with_session` / `async_session_scope`（embedding、document_parse、crawl 等）
- [x] 3.3 迁移 tasks/scheduler（document_parse、web_crawler、embedding、`get_scheduler.py` 等）上的 `@with_session` / `*_session_scope`
- [x] 3.4 迁移 agent tools / llm_util / tool_limit 等上的 `@with_session`
- [x] 3.5 迁移 Service 中的 `async_session_scope` / `@with_session`（如 config/dict、vector、crawler executor、proxy pool、rerank、milvus_data_scope、document_embedding 等）
- [x] 3.6 清理 Service 内无事务边界的直接 `get_current_session()` / 手动 `commit`（改为 DAO 或显式 `@transactional`）

## 4. 测试与文档

- [x] 4.1 更新 `test_transactional.py`：删除 with_session / session_scope 用例；新增 BaseDao 隐式短事务与 join 外层事务用例；断言无事务时 `get_current_session` 抛错
- [x] 4.2 修复依赖 `async_session_scope` 的其它测试（如 retrieval live 测试）
- [x] 4.3 更新 `docs/infrastructure/注解式事务管理.md`、`docs/architecture/中间件链与注解切面.md` 及相关架构文档，反映「Session 仅来自事务」与 BaseDao / PageUtil 约定
