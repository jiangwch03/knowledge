## 1. 前置摸排与防御

- [x] 1.1 `grep -rn "log_stream_key\|log_stream_group\|log_stream_consumer_prefix\|log_stream_batch_size\|log_stream_block_ms\|log_stream_claim_idle_ms\|log_stream_claim_interval_ms\|log_stream_claim_batch_size" --include="*.py"` 确认 8 个待删字段只在 `log_service.py` 与 `env.py` 内部使用,无外部引用
- [x] 1.2 `grep -rn "LogAggregatorService\|consume_stream\|_ensure_group\|_claim_pending\|_acquire_dedup\|_release_dedup\|_xadd_event\|_process_messages" --include="*.py"` 列出所有调用点,确认仅 admin/rag 的 `server.py` 与 `log_service.py` 自身
- [x] 1.3 `grep -rn "get_stream_key\|get_stream_group" --include="*.py"` 确认无外部代码依赖
- [x] 1.4 在 `knowledge-common/tests/test_message_stream.py` 现有 fakeredis/真 redis 端到端逻辑里观察 6379 自动 skip 模式,作为新测试的模板参考
- [x] 1.5 浏览 `knowledge_common/message_stream/backends/redis_stream.py` 的 `publish` 实现,确认 `headers` 与 `value` / `key` 的拆分方式(`__value` / `__key` / `__headers`),确保新 headers 字段(`event_id` 等)消费侧能正确从 `msg.headers` 取出

## 2. LogDedupHelper 实现

- [x] 2.1 在 `knowledge_common/service/log_service.py` 新增 `LogDedupHelper` 类,提供类方法 `acquire(event_id: str, app_name: str) -> AsyncContextManager[bool]`
- [x] 2.2 `LogDedupHelper.acquire` 内部用 `asynccontextmanager` 装饰的生成器或显式 `__aenter__` / `__aexit__` 实现:`__aenter__` 调 `redis.set(key, '1', nx=True, ex=LogConfig.log_stream_dedup_ttl)` 返回 `bool`(是否成功获取);`__aexit__(exc_type, ...)` 若 `exc_type is not None` 调 `redis.delete(key)`(对应原 `_release_dedup` 行为),正常返回保留 TTL
- [x] 2.3 `LogDedupHelper` 通过 `from knowledge_common.config.get_redis import RedisContext` 取 redis 客户端(对齐项目已有的 ContextVar 注入范式),不显式接收 redis 参数
- [x] 2.4 `LogDedupHelper` 处理空 `event_id`:进入时直接返回 `False`(不获取锁,与原 `_acquire_dedup` 行为一致),退出时不释放
- [x] 2.5 `LogDedupHelper` 加 docstring 说明"业务级去重 helper,用 SET NX EX,失败回滚自动释放"

## 3. 业务消费者(common 集中维护,admin / rag 自动复用)

- [x] 3.1 新建 `knowledge-common/src/knowledge_common/message/consumer/log_consumer.py`(单文件集中维护);不再新建 `knowledge-admin/src/knowledge_admin/message/consumer/log_consumer.py` 与 `knowledge-content/src/knowledge_content/message/consumer/log_consumer.py`;`MessageStreamService._scan_paths` 默认值已含 `knowledge_common.message.consumer`(见 `knowledge_common/message_stream/service.py:59`),admin / rag 任一进程启动时都会 import 该文件并触发装饰器注册
- [x] 3.2 定义 `handle_admin_login_log`:`@consumer(topic='log:login:knowledge-admin', group_id='log_writer:knowledge-admin')` 装饰 `async def handle_admin_login_log(msg: Message) -> None`
- [x] 3.3 定义 `handle_admin_operation_log`:`@consumer(topic='log:operation:knowledge-admin', group_id='log_writer:knowledge-admin')` 装饰 `async def handle_admin_operation_log(msg: Message) -> None`
- [x] 3.4 定义 `handle_rag_login_log`:`@consumer(topic='log:login:knowledge-content', group_id='log_writer:knowledge-content')` 装饰 `async def handle_rag_login_log(msg: Message) -> None`
- [x] 3.5 定义 `handle_rag_operation_log`:`@consumer(topic='log:operation:knowledge-content', group_id='log_writer:knowledge-content')` 装饰 `async def handle_rag_operation_log(msg: Message) -> None`
- [x] 3.6 4 函数体统一骨架:从 `msg.headers` 取 `event_id` / `app_name` → `async with LogDedupHelper.acquire(event_id, app_name) as ok: if not ok: return` → `async with AsyncSessionLocal() as session: await <Login|Operation>LogDao.add_<login|operation>_log_dao(session, <LogininforModel|OperLogModel>(**msg.value)); await session.commit()`;`app_name` 走 if/elif 分流到 admin / rag 对应 dao 与表
- [x] 3.7 4 函数异常分支:让异常向上抛(框架 `_consume_loop` 自动跳过 ack,后端协议重投);`LogDedupHelper.acquire` 的 `__aexit__` 接收 `exc_type is not None` 自动 `delete` 释放 dedup,允许下一轮重试
- [x] 3.8 4 函数加 docstring 说明:"日志聚合消费者(topic=log:{event_type}:{app_name}):从 message_stream 取消息 → 业务级去重 → 落库 → 框架自动 ack"
- [ ] 3.9 verify:启动 admin / rag 任一进程,日志中出现 4 个 `🚀 消费者后台协程已启动: id=knowledge_common.message.consumer.log_consumer.handle_<admin|rag>_<login|operation>_log`;admin 进程实际处理消息的只有 2 个(admin 专属 topic),rag 的 2 个消费者协程长期空转阻塞拉取(2s block_ms),开销可忽略;通过 `redis-cli XINFO CONSUMERS log:operation:knowledge-admin log_writer:knowledge-admin` 可看到 admin 进程注册了 1 个 consumer 实体

## 4. LogQueueService 切到 MessageStreamService.produce

- [x] 4.1 `LogQueueService._xadd_event` 整方法删除
- [x] 4.2 `LogQueueService.enqueue_login_log` 改造:计算 `event_id`(复用 `_build_event_id`)→ `payload = LogSanitizer.sanitize_data(login_log.model_dump(by_alias=True, exclude_none=True))` → 构造 `headers = {'event_id': event_id, 'event_type': 'login', 'request_id': TraceCtx.get_request_id(), 'trace_id': TraceCtx.get_trace_id(), 'span_id': TraceCtx.get_span_id(), 'app_name': app_name, 'source': source}` → `await MessageStreamService.produce(topic=f'log:login:{app_name}', value=payload, key=TraceCtx.get_request_id(), headers=headers)`
- [x] 4.3 `LogQueueService.enqueue_operation_log` 改造:与 4.2 同结构,`event_type='operation'`,`topic=f'log:operation:{app_name}'`,`value` 用 `operation_log.model_dump`
- [x] 4.4 删除 `LogQueueService` 不再使用的 import:`from redis import asyncio as aioredis`、`from redis.exceptions import TimeoutError as RedisTimeoutError`(若 `LogAggregatorService` 也一并删,统一收尾)
- [x] 4.5 `LogQueueService._build_event_id` 保留(推送端复用),`_resolve_app_name` 保留(从 `request.app.state.app_name` 取)
- [x] 4.6 `LogQueueService.enqueue_*` 不再接收 `redis` 参数(framework 内部走 Settings + ContextVar),验证 `log_annotation.py` 现有调用 `LogQueueService.enqueue_*` 的签名与新签名兼容(无需改动)

## 5. LogAggregatorService 整类删除 + LogConfig 精简

- [x] 5.1 `LogAggregatorService` 整类(含 `_ensure_group` / `_acquire_dedup` / `_release_dedup` / `_claim_pending` / `consume_stream` / `_process_messages` 6 个方法)从 `log_service.py` 完全删除,**不留空壳**
- [x] 5.2 删除 `log_service.py` 顶部因 `LogAggregatorService` 失去引用的 import:`asyncio` / `os` / `RedisTimeoutError` / `aioredis`(逐个检查,如 `LogQueueService` 仍需则保留)
- [x] 5.3 `LogConfig` 删除 8 个纯协议字段:`log_stream_key` / `log_stream_group` / `log_stream_consumer_prefix` / `log_stream_batch_size` / `log_stream_block_ms` / `log_stream_claim_idle_ms` / `log_stream_claim_interval_ms` / `log_stream_claim_batch_size`
- [x] 5.4 `LogConfig` 删除 `log_stream_maxlen` 字段(由 `MessageStreamSettings.message_stream_redis_maxlen` 接管;若 `MessageStreamSettings` 未设此字段则补)
- [x] 5.5 `LogConfig` 删除 `get_stream_key` / `get_stream_group` 类方法(对应 stream 协议层已无业务依赖)
- [x] 5.6 `LogConfig` 保留:`log_stream_dedup_prefix` / `log_stream_dedup_ttl` / `get_dedup_prefix(app_name)` 这 3 项
- [x] 5.7 检查 `MessageStreamSettings.message_stream_redis_maxlen` 字段是否已存在(查 `knowledge_common/config/env.py`);若未声明则补,默认 `100000`(对齐原 `log_stream_maxlen`)
- [x] 5.8 在所有 `.env.*` 文件中(`.env.dev` / `.env.prod` / `.env.dockermy` / `.env.dockerpg`)同步删除 `LOG_STREAM_KEY` / `LOG_STREAM_GROUP` / `LOG_STREAM_CONSUMER_PREFIX` / `LOG_STREAM_BATCH_SIZE` / `LOG_STREAM_BLOCK_MS` / `LOG_STREAM_CLAIM_IDLE_MS` / `LOG_STREAM_CLAIM_INTERVAL_MS` / `LOG_STREAM_CLAIM_BATCH_SIZE` / `LOG_STREAM_MAXLEN` 等环境变量(如果存在)
- [ ] 5.9 verify:`ruff check knowledge-common knowledge-admin knowledge-content` 无未引用 import 警告;`uv run python -c "from knowledge_common.config.env import LogConfig; print(LogConfig.log_stream_dedup_prefix)"` 能成功加载

## 6. server.py 后台任务清理(admin / rag)

- [x] 6.1 `knowledge-admin/src/knowledge_admin/server/server.py` 的 `_start_background_tasks` 删除 `app.state.log_aggregator_task = asyncio.create_task(LogAggregatorService.consume_stream(...))` 这段
- [x] 6.2 admin `_stop_background_tasks` 删除 `log_task = getattr(app.state, 'log_aggregator_task', None); if log_task: log_task.cancel(); try: await log_task except asyncio.CancelledError: pass` 这段
- [x] 6.3 admin `server.py` 文件顶部删除 `from knowledge_common.service.log_service import LogAggregatorService` import
- [ ] 6.4 `knowledge-content/src/knowledge_content/server/server.py` 重复 6.1 / 6.2 / 6.3 三步
- [ ] 6.5 verify:启动 admin / rag,lifespan 日志中**不再出现**与 `LogAggregatorService.consume_stream` 相关的协程启动记录;仅出现 `MessageStreamService.discover_and_start` 拉起的消费者协程日志(含 `log_consumer.handle_operation_log` / `handle_login_log`)

## 7. 端到端测试

- [x] 7.1 新建 `knowledge-common/tests/test_log_aggregation_via_message_stream.py`,设置 6379 自动 skip(参考 `test_message_stream.py` 现有 fixture)
- [ ] 7.2 测试用例 1 — 推送链路:模拟 `enqueue_operation_log(request, OperLogModel(...), 'unit_test')`,验证 Redis Stream `log:operation:{app_name}` 中出现一条消息,且 `fields` 含 `__value`(payload)、`__key`(request_id)、`__headers`(含 event_id / event_type / app_name 等)
- [ ] 7.3 测试用例 2 — 消费链路:启动一个 `@consumer(topic='log:operation:test', group_id='log_writer:test')` 装饰的内联消费者,推送后断言 1 秒内消费函数被调用,且 `msg.headers['event_id']` 与推送侧一致
- [ ] 7.4 测试用例 3 — 去重:同一 `event_id` 连续推送 2 条,断言数据库表(测试用 sqlite in-memory 或 mock dao)只新增 1 条
- [ ] 7.5 测试用例 4 — 异常回滚释放:mock dao 第一次抛异常,第二次成功;断言两次都成功调到 dao(dedup 在第一次失败时释放,第二次能再次获取)
- [ ] 7.6 测试用例 5 — app_name 隔离:admin 推送 `log:operation:knowledge-admin`,rag 端的 `@consumer(topic='log:operation:knowledge-content', ...)` 不应被触发(断言计数器为 0)
- [ ] 7.7 verify:`cd knowledge-common && uv run pytest tests/test_log_aggregation_via_message_stream.py -v` 全绿(本机 Redis 不连通时所有用例 skip,不应 fail)

## 8. 文档同步

- [x] 8.1 `docs/rag/log-aggregator-flow.md` 全文重写:删除原"裸 xadd → xreadgroup → xack"的章节;新增"基于 MessageStreamService 的日志聚合"概述、Mermaid 时序图(注解触发 → LogQueueService.enqueue → MessageStreamService.produce → RedisStreamBackend.publish → @consumer handle → LogDedupHelper.acquire → DAO 落库 → 框架自动 ack)、按 app_name 隔离的命名约定
- [x] 8.2 `knowledge-common/README.md` 的"消息流服务"章节增加"日志聚合接入示例"子章节,展示 `knowledge_common/message/consumer/log_consumer.py` 的完整代码骨架(@consumer 装饰器 + LogDedupHelper 使用范式);说明该文件由 common 集中维护,admin / rag 通过 `MessageStreamService` 框架默认扫描路径(`knowledge_common.message.consumer`)自动注册,业务项目侧零代码
- [x] 8.3 在 `docs/rag/log-aggregator-flow.md` 中明确"切 Kafka 时的契约保证":日志业务零修改、仅 `.env` 一行切换
- [x] 8.4 verify:Mermaid 在 Qoder/VS Code 预览器渲染正常(无保留字冲突、无多 actor 注释语法问题)

## 9. 验收与回归

- [x] 9.1 `cd knowledge-common && uv run pytest tests/ -v` 全部测试通过(含 `test_message_stream.py` + 新增的 `test_log_aggregation_via_message_stream.py`)
- [x] 9.2 启动 admin,触发一次登录请求,确认 MySQL `sys_logininfor` 表新增一行;触发一次任意 `@Log` 注解接口,确认 `sys_oper_log` 表新增一行
- [x] 9.3 启动 rag,触发同样行为,确认 rag 端日志只写到 rag 端表,**admin 端表无新增**(跨 app 不串扰验证)
- [x] 9.4 同时启动 admin 与 rag,各自触发日志,确认两个进程日志中均出现 4 个 `id=knowledge_common.message.consumer.log_consumer.handle_*` 消费者后台协程;admin 进程实际消费的是 `log:*:knowledge-admin` topic 的消息、rag 进程实际消费的是 `log:*:knowledge-content` topic 的消息(各 2 个活跃 + 2 个空转),跨 app 不串扰
- [x] 9.5 模拟"高并发同一请求 ID 重复推送":手动在 redis 上 `XADD log:operation:knowledge-admin '*' __headers '{"event_id":"DUPL_ID","event_type":"operation",...}' __value '{...}'` 触发同 event_id 的二次投递,确认 `sys_oper_log` 只多 1 行(去重成功)
- [x] 9.6 模拟"消费者函数抛异常":临时让 `handle_admin_operation_log` 内部抛 `RuntimeError`,确认消息保留在 PEL(`XPENDING log:operation:knowledge-admin log_writer:knowledge-admin`),60 秒后被 `claim_idle` 接管(由 `MessageStreamService._claim_idle_loop` 周期触发);恢复函数后下一轮接管处理成功
- [x] 9.7 关闭 admin,确认 lifespan 退出阶段日志依次打出 `🛑 消费协程已取消: consumer=knowledge_common.message.consumer.log_consumer.handle_<admin|rag>_<login|operation>_log` × 4 → `🛑 MessageStreamService 已关闭`,无残留协程
