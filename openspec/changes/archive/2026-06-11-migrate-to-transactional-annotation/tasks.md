## 1. knowledge-common DAO 层改造

- [x] 1.1 改造 `config_dao.py`：所有方法删除 `db` 参数，方法体改为 `db = get_current_session()`
- [x] 1.2 改造 `dict_dao.py`：所有方法（SysDictTypeDao + SysDictDataDao）删除 `db` 参数
- [x] 1.3 改造 `job_dao.py`：所有方法删除 `db` 参数
- [x] 1.4 改造 `job_log_dao.py`：所有方法删除 `db` 参数
- [x] 1.5 改造 `log_dao.py`：所有方法删除 `db` 参数
- [x] 1.6 改造 `user_login_dao.py`：所有方法删除 `db` 参数
- [x] 1.7 改造 `page_util.py`：`PageUtil.paginate` 删除 `db` 参数，内部改为 `db = get_current_session()`

## 2. knowledge-common Service 层改造

- [x] 2.1 改造 `config_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback，内部改调 `get_current_session()`
- [x] 2.2 改造 `dict_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 2.3 改造 `log_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 2.4 改造 `job_log_service.py`：所有方法（含同步方法）删除 `query_db` 参数，异步写操作加 `@transactional()`，同步写操作保留 `@transactional_sync()`，移除 try/commit/rollback
- [x] 2.5 改造 `login_user_service.py`：`get_current_user` 删除 `query_db: AsyncSession = Depends(get_db)` 参数，内部改为 `get_current_session()`
- [x] 2.6 改造 `pre_auth.py`：`__call__` 删除 `db: AsyncSession = Depends(get_db)` 参数，内部改为 `get_current_session()`
- [x] 2.7 改造 `log_consumer.py`：`_persist_log` 改用 `@transactional()` 包裹，删除手动 `AsyncSessionLocal()` + `commit()`，DAO 调用不再传 session

## 3. knowledge-admin DAO 层改造

- [x] 3.1 改造 `post_dao.py`：所有方法删除 `db` 参数
- [x] 3.2 改造 `role_dao.py`：所有方法删除 `db` 参数
- [x] 3.3 改造 `dept_dao.py`：所有方法删除 `db` 参数
- [x] 3.4 改造 `menu_dao.py`：所有方法删除 `db` 参数
- [x] 3.5 改造 `user_dao.py`：所有方法删除 `db` 参数
- [x] 3.6 改造 `notice_dao.py`：所有方法删除 `db` 参数
- [x] 3.7 改造 `ai_chat_dao.py`：所有方法删除 `db` 参数
- [x] 3.8 改造 `ai_model_dao.py`：所有方法删除 `db` 参数
- [x] 3.9 改造 `login_dao.py`：所有方法删除 `db` 参数

## 4. knowledge-admin Service 层改造

- [x] 4.1 改造 `post_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 4.2 改造 `role_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 4.3 改造 `dept_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 4.4 改造 `menu_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 4.5 改造 `user_service.py`：所有方法删除 `query_db` 参数，写操作加 `@transactional()`，移除 try/commit/rollback
- [x] 4.6 改造 `job_service.py`：写操作方法删除 `query_db` 参数，加 `@transactional()`，移除 try/commit/rollback

## 5. knowledge-admin Controller 层改造

- [x] 5.1 改造 `post_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`
- [x] 5.2 改造 `role_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`
- [x] 5.3 改造 `dept_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`
- [x] 5.4 改造 `menu_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`
- [x] 5.5 改造 `user_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`
- [x] 5.6 改造 `notice_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`（如有）
- [x] 5.7 改造 `job_controller.py`：所有路由删除 `DBSessionDependency()` 注入，调用 Service 不传 `query_db`（如有）

## 6. 验证

- [x] 6.1 验证 knowledge-common 全部改造后编译通过
- [x] 6.2 验证 knowledge-admin 全部改造后编译通过
- [x] 6.3 启动 knowledge-admin，验证 CRUD 操作正常（新增/编辑/删除岗位、角色、字典类型）
- [x] 6.4 验证嵌套事务场景正常（角色删除级联删除角色菜单/部门关联）
- [x] 6.5 验证异常回滚正常（重复编码创建失败后无脏数据）
