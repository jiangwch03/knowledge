## Why

上一个 change(`2026-06-11-message-stream-service-kafka-style-api`)在 `knowledge-common/message_stream/` 沉淀了 `MessageStreamService` 门面(支持 Redis Stream / Kafka 双后端,Kafka 风格 API),但**日志聚合(`LogQueueService` + `LogAggregatorService`)仍在 `log_service.py` 里直接调 `xadd` / `xreadgroup` / `xack` / `xautoclaim` / `xgroup_create` 等裸协议接口**,与新框架形成"双路日志栈":同一段 Redis Stream 协议代码在两处维护,切 Kafka 时还要为日志单独写迁移,违背了新框架"切后端零修改业务"的承诺,也让 `MessageStreamService` 与现有业务消费者出现"框架已就绪 / 业务未接入"的尴尬状态。本 change 完成原方案 design.md 明确写到的"阶段 2:日志模块迁移"——把日志聚合接入新框架,删除冗余协议代码,把日志业务也带进"切 Kafka 零修改"承诺范围。

## What Changes

- **新增 `knowledge_admin.message.consumer.log_consumer` 与 `knowledge_content.message.consumer.log_consumer`**:用 `@consumer(topic, group_id)` 装饰器声明 admin / rag 各自的"操作日志"与"登录日志"消费者,落库逻辑迁移自 `LogAggregatorService._process_messages`。
- **`LogQueueService.enqueue_login_log` / `enqueue_operation_log` 改用 `MessageStreamService.produce`**:删除内部 `_xadd_event` 直调 `redis.xadd` 的实现,改为 `await MessageStreamService.produce(topic=..., value=payload, key=request_id, headers={...})`,业务幂等键(`event_id`)写进 `headers`,延续原"按 request_id+log_type+source 计算 md5"的契约。
- **`LogAggregatorService.consume_stream` 整体移除**:取消 `_ensure_group` / `_claim_pending` / `_xadd_event` / `_acquire_dedup` / `_release_dedup` / `_process_messages` 等裸 Redis Stream 协议方法;落库与去重职责下沉到业务侧消费者函数。**BREAKING**(对内部 API,业务方未调用 `LogAggregatorService` 公共方法)。
- **`server.py` 中 `_start_background_tasks` 删除 `app.state.log_aggregator_task = asyncio.create_task(LogAggregatorService.consume_stream(...))`**:日志消费协程改由 `MessageStreamService.discover_and_start()` 统一拉起,`_stop_background_tasks` 同步删除对应的 cancel 逻辑;消息流服务的 `register_consumer_paths` 已在前一个 change 中接入,本 change 直接复用。
- **按 `app_name` 隔离改为按 topic 命名隔离**:延续原"admin 端只产销 `log:stream:knowledge-admin`、rag 端只产销 `log:stream:knowledge-content`"的契约,新框架下表达为 `topic = log:operation:{app_name}` / `log:login:{app_name}`,消费者用同样的 topic 订阅;`group_id` 仍按 app 隔离,确保跨 app 不串扰。
- **`LogConfig` 精简**:`log_stream_key` / `log_stream_group` / `log_stream_consumer_prefix` / `log_stream_batch_size` / `log_stream_block_ms` / `log_stream_claim_idle_ms` / `log_stream_claim_interval_ms` / `log_stream_claim_batch_size` 等纯协议字段全部移除(由 `MessageStreamService` 内部消费参数兜底);`log_stream_maxlen` 保留并迁移到 `MessageStreamSettings.message_stream_redis_maxlen`(已在前 change 提供),后续 `LogConfig` 只保留 `log_stream_dedup_prefix` / `log_stream_dedup_ttl` 这两个"业务级去重"配置以及 `get_dedup_prefix(app_name)` 拼接方法。
- **去重逻辑迁移到消费者函数**:`_acquire_dedup` / `_release_dedup` 行为不变,落到 `LogDedupHelper`(放在 `knowledge_common/service/log_service.py` 业务侧)由消费者主动调用——业务方在消费函数内手动调 dedup helper,失败回滚时主动释放,与新框架"业务自管幂等键"埋点契约一致(对应已归档 spec "切 Kafka 零返工的 4 个埋点"第 1 条:业务用业务 ID 做幂等键,不依赖消息 ID)。
- **文档同步**:`docs/rag/log-aggregator-flow.md` 全文重写为"基于 MessageStreamService 的日志聚合流程",删除裸协议章节;`knowledge-common/README.md` 的消息流服务章节增加"日志聚合接入示例"作为业务接入参考。

## Capabilities

### New Capabilities

- `log-aggregation`:日志聚合(操作日志、登录日志)作为业务方接入 `message-stream-service` 的契约,涵盖 topic 命名约定、消费者位置、按 app_name 隔离的 group/topic 策略、业务级去重、落库语义、与 `MessageStreamService` 的衔接方式。

### Modified Capabilities

(无 — `message-stream-service` 框架契约本身不变,本 change 只是业务接入)

## Impact

- **修改代码**
  - `knowledge-common/src/knowledge_common/service/log_service.py`:删除 `LogAggregatorService.consume_stream` / `_ensure_group` / `_claim_pending` / `_xadd_event` / `_process_messages` 等裸协议方法;`LogQueueService.enqueue_login_log` / `enqueue_operation_log` 改用 `MessageStreamService.produce`;新增 `LogDedupHelper`(包装去重 set+nx 语义)。
  - `knowledge-common/src/knowledge_common/config/env.py`:`LogConfig` 精简(参见 What Changes 第 6 条)。
  - `knowledge-admin/src/knowledge_admin/server/server.py`:`_start_background_tasks` 移除 `log_aggregator_task`,`_stop_background_tasks` 同步移除 cancel 逻辑。
  - `knowledge-content/src/knowledge_content/server/server.py`:同 admin。
- **新增代码**
  - `knowledge-admin/src/knowledge_admin/message/consumer/log_consumer.py`:`@consumer(topic='log:operation:knowledge-admin', group_id='log_writer:knowledge-admin')` 装饰的 admin 端登录/操作日志落库消费者。
  - `knowledge-content/src/knowledge_content/message/consumer/log_consumer.py`:rag 端同上,topic / group_id 用 rag 的 app_name 后缀。
  - `knowledge-common/tests/test_log_aggregation_via_message_stream.py`:端到端测试,验证 produce → consume → 落库 → 去重 → ack 全链路。
- **删除代码**
  - `LogAggregatorService` 全类删除(或保留空壳作为兼容窗口,具体由 design 决定)。
  - `LogConfig.log_stream_*` 中纯协议字段(8 个)删除。
  - `server.py` 中 `log_aggregator_task` 相关代码块删除。
- **文档**
  - `docs/rag/log-aggregator-flow.md`:全文重写,基于新框架描述流程图与时序图。
  - `knowledge-common/README.md`:消息流服务章节增加"日志聚合接入示例"。
- **依赖**
  - 不引入新依赖,完全基于已归档 change 提供的 `MessageStreamService` 与 `RedisStreamBackend`。
  - 跑通 Kafka 后端联调留给后续 change(本 change 用 Redis Stream 后端验收)。
- **风险**
  - 双路并存窗口:迁移期可能短暂存在"旧 stream key `log:stream` 还有未消费消息 + 新 topic `log:operation:{app_name}` 已开始接收新消息"的局面,需要在 Migration Plan 中说明迁移窗口或一次性切换策略。
  - 去重 helper 下沉到业务侧后,业务方必须**正确处理 dedup 失败回滚释放**(原 `_process_messages` 在 `except` 分支统一 `_release_dedup`),`LogDedupHelper` 必须把"acquire → 业务 → fail 释放"包装成 `async with` 上下文管理器,降低业务方踩坑概率。
  - 启动顺序:`MessageStreamService.discover_and_start` 必须在 `Redis 连接池可用之后`、`首条日志被 enqueue 之前`,这与 server.py 现有 lifespan 顺序兼容(已在前 change 中校验)。
  - 多进程/多副本场景:框架已通过消费组协议(Redis Stream 的 `xreadgroup` `LAST_DELIVERED_ID`)保证同 group 不重复,本 change 直接复用,无新增风险。
