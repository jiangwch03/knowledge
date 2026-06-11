## ADDED Requirements

### Requirement: 日志聚合通过 MessageStreamService 接入

日志聚合(操作日志、登录日志)SHALL 通过 `MessageStreamService.produce(topic, value, key, headers)` 推送、通过 `@consumer(topic, group_id)` 装饰的消费者落库,SHALL NOT 在业务代码中直接调用 `xadd` / `xreadgroup` / `xack` / `xautoclaim` / `xgroup_create` 等 Redis Stream 原生协议接口。日志业务作为 `message-stream-service` 的标准业务方,SHALL 与该 capability 提供的契约(Kafka 风格命名、装饰器注册、4 个埋点)完全对齐。

#### Scenario: 操作日志推送走 produce 方法
- **WHEN** `@Log` 注解触发 `LogQueueService.enqueue_operation_log(request, operation_log, source)`
- **THEN** 内部 SHALL 调用 `await MessageStreamService.produce(topic=f'log:operation:{app_name}', value=payload, key=request_id, headers={'event_id': ..., 'event_type': 'operation', 'trace_id': ..., 'span_id': ..., 'app_name': ..., 'source': ...})`,SHALL NOT 调用任何 `redis.xadd` 或其包装方法

#### Scenario: 登录日志推送走 produce 方法
- **WHEN** 登录成功 / 失败链路触发 `LogQueueService.enqueue_login_log(request, login_log, source)`
- **THEN** 内部 SHALL 调用 `await MessageStreamService.produce(topic=f'log:login:{app_name}', value=payload, key=request_id, headers={'event_id': ..., 'event_type': 'login', ...})`,SHALL NOT 调用 `redis.xadd`

#### Scenario: 日志消费者由装饰器声明
- **WHEN** 框架 `MessageStreamService.discover_and_start()` 扫描业务消费者路径
- **THEN** 业务侧 SHALL 提供 `@consumer(topic='log:operation:{app_name}', group_id='log_writer:{app_name}')` 装饰的 async 函数(放在 `knowledge_admin.message.consumer.log_consumer` / `knowledge_rag.message.consumer.log_consumer`),由框架自动拉起后台消费协程,业务侧 SHALL NOT 自行 `asyncio.create_task(LogAggregatorService.consume_stream(...))`

### Requirement: 按 app_name 隔离的 topic / group 命名约定

日志聚合 SHALL 沿用"按 app_name 自产自销"语义:admin 端只产销 admin 的日志、rag 端只产销 rag 的日志、彼此不串扰。隔离 SHALL 通过 topic 命名后缀 `:{app_name}` 与消费组命名后缀 `:{app_name}` 共同表达。

#### Scenario: admin 端 topic / group 命名
- **WHEN** `app.state.app_name == 'knowledge-admin'`
- **THEN** 操作日志 topic SHALL 为 `log:operation:knowledge-admin`,登录日志 topic SHALL 为 `log:login:knowledge-admin`,消费组 SHALL 为 `log_writer:knowledge-admin`

#### Scenario: rag 端 topic / group 命名
- **WHEN** `app.state.app_name == 'knowledge-rag'`
- **THEN** 操作日志 topic SHALL 为 `log:operation:knowledge-rag`,登录日志 topic SHALL 为 `log:login:knowledge-rag`,消费组 SHALL 为 `log_writer:knowledge-rag`

#### Scenario: 跨 app 不串扰
- **WHEN** admin 与 rag 在同一 Redis 实例上同时运行,且都注册了日志消费者
- **THEN** admin 消费者 SHALL 只消费 `log:*:knowledge-admin` 系列 topic,rag 消费者 SHALL 只消费 `log:*:knowledge-rag` 系列 topic,日志条目 SHALL NOT 出现在另一端的数据库表里

### Requirement: 业务级去重契约

日志聚合 SHALL 在消费者侧通过 `LogDedupHelper`(基于 Redis SET NX + EX)实现业务级去重,确保同一条日志事件(由 `request_id + log_type + source` 计算的 md5)SHALL NOT 因为消息重复投递(重试 / claim_idle 接管 / 多消费者场景)被写入数据库多次。去重键 SHALL 按 app_name 隔离,SHALL 使用 `LogConfig.get_dedup_prefix(app_name)` 拼接。

#### Scenario: 重复消息只落库一次
- **WHEN** 同一 `event_id` 的消息被框架重试两次或被 `claim_idle` 接管一次
- **THEN** 第一次消费 SHALL 成功落库且 dedup key 被占用 (`SET NX` 返回 True),后续消费 SHALL 检测到 dedup key 存在并直接 ack 跳过,数据库 SHALL 只新增一条记录

#### Scenario: 落库失败回滚释放 dedup
- **WHEN** 消费者 acquire dedup 成功 → 调用 dao 落库时抛异常 → session.rollback()
- **THEN** `LogDedupHelper` SHALL 在异常分支主动 `delete` dedup key(对应原 `_release_dedup` 行为),确保后续重试可以再次落库,SHALL NOT 因为 dedup 未释放导致消息永久丢失

#### Scenario: 去重 helper 提供 async 上下文管理器
- **WHEN** 业务消费者使用 `async with LogDedupHelper.acquire(event_id, app_name) as ok:`
- **THEN** 上下文 SHALL 在 `__aenter__` 中调 `SET NX EX`,`ok` SHALL 反映是否首次获取;`__aexit__` 时如果业务抛异常 SHALL 自动 `delete` 释放,正常返回 SHALL NOT 释放(保留 TTL 内的去重窗口)

### Requirement: 业务消费者的落库与 ack 语义

日志消费者函数 SHALL 是 `async def handle(msg: Message) -> None` 签名,函数体 SHALL 自管事务、自管去重、自管异常,正常返回触发框架自动 ack,抛异常触发框架不 ack 由后端协议兜底(对应已归档 `message-stream-service` spec "业务正常返回自动 ack" / "业务抛异常自动不 ack" 两个场景)。

#### Scenario: 单批消息落库走 AsyncSessionLocal
- **WHEN** 消费者函数收到 `msg`
- **THEN** 函数 SHALL 在 `async with AsyncSessionLocal() as session:` 中调对应 DAO(`LoginLogDao.add_login_log_dao` / `OperationLogDao.add_operation_log_dao`)并 `await session.commit()`;事务 SHALL 与日志业务对齐(每条消息独立提交),SHALL NOT 跨多条消息共享同一 session

#### Scenario: 落库成功自动 ack
- **WHEN** 消费者函数正常返回(无异常)
- **THEN** 框架 SHALL 自动调 `backend.ack(topic, group_id, msg.offset)`,业务函数 SHALL NOT 直接调 `redis.xack` 或 `backend.ack`

#### Scenario: 落库失败由后端协议兜底
- **WHEN** 消费者函数因数据库连接异常抛 `SQLAlchemyError`
- **THEN** 框架 SHALL 捕获异常并跳过 ack,消息 SHALL 保留在 PEL(Redis Stream)或未 commit 偏移(Kafka),由 `claim_idle` 接管循环或重平衡机制重新投递

### Requirement: LogConfig 精简,纯协议字段下沉到 MessageStreamSettings

`LogConfig` SHALL 只保留"业务级"字段(`log_stream_dedup_prefix` / `log_stream_dedup_ttl` 以及 `get_dedup_prefix(app_name)` 拼接方法),SHALL 删除以下 8 个纯 Redis Stream 协议字段(由 `MessageStreamService` 内部消费参数 / `MessageStreamSettings` 兜底):`log_stream_key` / `log_stream_group` / `log_stream_consumer_prefix` / `log_stream_batch_size` / `log_stream_block_ms` / `log_stream_claim_idle_ms` / `log_stream_claim_interval_ms` / `log_stream_claim_batch_size`。`log_stream_maxlen` SHALL 由 `MessageStreamSettings.message_stream_redis_maxlen`(已在前一 change 提供)接管。

#### Scenario: 旧协议字段被删除
- **WHEN** 业务代码引用 `LogConfig.log_stream_key` / `log_stream_group` 等被删除字段
- **THEN** Python SHALL 抛 `AttributeError`,引导开发者改用 topic / group_id 语义(由消费者装饰器声明),不再有"通过 LogConfig 取裸协议参数"的路径

#### Scenario: MAXLEN 复用 MessageStreamSettings
- **WHEN** `RedisStreamBackend.publish` 内部需要 `maxlen` 参数
- **THEN** SHALL 从 `MessageStreamSettings.message_stream_redis_maxlen` 取值(已在 backends/factory.py 注入),业务方不再通过 `LogConfig.log_stream_maxlen` 配置

#### Scenario: 业务级去重字段保留
- **WHEN** 消费者调 `LogConfig.get_dedup_prefix('knowledge-admin')`
- **THEN** SHALL 返回 `'log:dedup:knowledge-admin'`,与原行为一致(为去重 helper 提供按 app 隔离的 key 前缀)

### Requirement: 服务器启动顺序与后台任务移除

`knowledge_admin.server.server` 与 `knowledge_rag.server.server` 的 `_start_background_tasks` SHALL NOT 再创建 `app.state.log_aggregator_task`,日志消费协程 SHALL 由 `MessageStreamService.discover_and_start()`(在 `_init_message_stream` 中调用)统一拉起;`_stop_background_tasks` SHALL 同步删除对 `log_aggregator_task` 的 cancel 逻辑。

#### Scenario: 后台任务不再包含 log_aggregator_task
- **WHEN** 应用启动 lifespan 走完 `_start_background_tasks`
- **THEN** `app.state` SHALL NOT 出现 `log_aggregator_task` 属性,日志消费 SHALL 完全由 `MessageStreamService._tasks` 字典中按 `consumer_id` 注册的协程承载

#### Scenario: 关闭顺序保持 message_stream 优先
- **WHEN** lifespan 退出阶段
- **THEN** SHALL 先调 `await MessageStreamService.shutdown()`(取消所有消费协程)、再调 `_stop_background_tasks`(关 Redis / 调度器),与已归档 `message-stream-service` spec "shutdown 关闭钩子"场景对齐

### Requirement: 4 个埋点契约下沉到日志业务

日志聚合 SHALL 贯彻已归档 `message-stream-service` spec 中"切 Kafka 零返工的 4 个埋点":(1) 业务幂等键用 `event_id`(`md5(request_id+log_type+source)`),不依赖 Redis Stream 的消息 xid 或 Kafka 的 offset;(2) 顺序保证用 `key=request_id`,Redis 后端把 key 写进 payload,Kafka 后端会按 key 路由 partition;(3) 异常语义统一(消费者抛异常 = 框架不 ack = 后端协议兜底);(4) 业务状态(操作日志表 / 登录日志表)在关系库自管,不依赖消息中间件持有。

#### Scenario: 切 Kafka 时日志业务零修改
- **WHEN** `.env` 把 `MESSAGE_STREAM_BACKEND` 从 `redis` 改为 `kafka`
- **THEN** 日志聚合所有代码 SHALL 零修改:`@consumer` 装饰器、`MessageStreamService.produce` 调用、`LogDedupHelper`、`LoginLogDao` / `OperationLogDao` 全部保持原签名;只有 `RedisStreamBackend` 与 `KafkaStreamBackend` 在 factory 层切换

#### Scenario: 顺序由 request_id 保证
- **WHEN** 同一请求(同 `request_id`)在短时间内产生多条 operation 日志(例:接口内多次审计)
- **THEN** Redis 后端 SHALL 把 key 写进 payload(同 stream 内仍按 xid 单调递增),Kafka 后端 SHALL 把 key 作为 partition key(同 request_id 始终路由到同 partition,保证落库顺序)

#### Scenario: 日志业务状态自管
- **WHEN** 日志成功落库后
- **THEN** 业务状态(已写入 `sys_oper_log` / `sys_logininfor` 表)SHALL 完全由关系库表达,SHALL NOT 在 Redis Stream / Kafka 中持有"是否已落库"标志
