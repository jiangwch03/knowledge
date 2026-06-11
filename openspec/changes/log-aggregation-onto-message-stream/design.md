## Context

### 现状
- 已归档 change `2026-06-11-message-stream-service-kafka-style-api` 在 `knowledge_common/message_stream/` 沉淀了 `MessageStreamService` 门面、`@consumer` 装饰器、`StreamBackend` 抽象、Redis Stream / Kafka 双后端、`init_from_settings` 配置驱动入口
- `knowledge-admin/server/server.py` 与 `knowledge-rag/server/server.py` 已接入 `MessageStreamService.init_from_settings` + `register_consumer_paths(['knowledge_xxx.message.consumer'])` + `discover_and_start()`,但**消费者目录下只有 `test_consumer.py`**,没有日志消费者
- 日志聚合仍在 `knowledge_common/service/log_service.py` 用裸 `redis.xadd` / `xreadgroup` / `xack` / `xautoclaim` / `xgroup_create`,通过 `LogQueueService` 推送、`LogAggregatorService.consume_stream` 在 `app.state.log_aggregator_task = asyncio.create_task(...)` 后台拉起
- `LogConfig` 含 11 个 `log_stream_*` 字段(8 个纯协议字段 + 3 个业务级字段)
- 按 `app_name` 隔离的"自产自销"已落地:`get_stream_key(app_name)` / `get_stream_group(app_name)` / `get_dedup_prefix(app_name)`,admin 与 rag 用各自的 stream key / group / dedup 前缀

### 约束
- 已归档框架的 6 个抽象方法签名(`publish` / `consume` / `ack` / `create_group` / `claim_idle` / `shutdown`)与 `Message` 字段不能因为日志接入而修改
- "按 app_name 自产自销"隔离契约必须延续,admin 端绝不能消费到 rag 端的日志
- 4 个埋点(业务 ID 自管 / 顺序用 key / 异常语义统一 / 业务状态自管)必须在日志业务上贯彻
- 不引入新依赖
- 不破坏 `@Log` 注解的对外契约(`enqueue_login_log` / `enqueue_operation_log` 方法签名保持)

### 利益相关方
- `knowledge-admin` / `knowledge-rag`:lifespan 启动顺序、新消费者文件位置
- `knowledge-common` 维护者:`log_service.py` 的删改、`LogConfig` 字段下沉、`LogDedupHelper` 新设计
- 未来切 Kafka 的工程师:本 change 是验证"业务零修改"承诺的关键样本

## Goals / Non-Goals

### Goals
1. 用 `@consumer(topic, group_id)` 装饰器声明日志消费者,删除 `LogAggregatorService.consume_stream` 等裸协议代码
2. 用 `await MessageStreamService.produce(topic, value, key, headers)` 替换 `LogQueueService` 内部的 `redis.xadd` 直调
3. 按 app_name 隔离用 `topic = log:{event_type}:{app_name}` + `group_id = log_writer:{app_name}` 表达,延续自产自销契约
4. 业务级去重(`LogDedupHelper`)用 async 上下文管理器包装,在 `__aexit__` 异常分支自动 release,业务方零踩坑
5. `LogConfig` 精简为只含业务级字段(dedup_prefix / dedup_ttl),纯协议字段全部删除
6. server.py 删除 `log_aggregator_task` 后台协程,完全靠 `MessageStreamService.discover_and_start()` 拉起
7. 跑通端到端测试:推送 → 消费 → 去重 → 落库 → ack 全链路

### Non-Goals
- 不重新设计 `MessageStreamService` 框架(框架契约保持)
- 不实现 Kafka 后端的日志业务联调(后续 change 跑 testcontainers)
- 不改 `LoginLogDao` / `OperationLogDao`(落库 SQL 与字段保持)
- 不改 `LogininforModel` / `OperLogModel`(VO 结构保持)
- 不改 `@Log` 注解的对外契约(`title` / `business_type` / `log_type` 等参数保持)
- 不引入"批量消费"语法(框架首版只做单条消费,日志业务同样单条)
- 不做"双路并存灰度":一次性切换,旧 stream 残留消息由 redis 自然过期(默认 maxlen=100000 + xtrim 兜底)

## Decisions

- **新消费者目录**:`knowledge_common/message/consumer/log_consumer.py`(单文件集中维护,代码一份),内含 4 个消费函数(admin/rag × login/operation),装饰器分别声明各自 topic;各项目独立部署时由 `MessageStreamService` 框架默认扫描路径(`_scan_paths` 默认值已含 `knowledge_common.message.consumer`,见 `knowledge_common/message_stream/service.py:59`)自动 import + 注册,业务项目侧零代码复制;不新建 `knowledge_admin/message/consumer/log_consumer.py` 与 `knowledge_rag/message/consumer/log_consumer.py`
- **topic 命名**:`log:{event_type}:{app_name}`,event_type ∈ `{login, operation}`;与原 stream key `log:stream:{app_name}` 形态对齐,语义升级为 Kafka 风格
- **group_id 命名**:`log_writer:{app_name}`,跨进程同 app 的多个 worker 共享,跨 app 不共享
- **`event_id` 进 headers,不进 payload**:headers 走 Kafka 元数据语义,payload 保留原"log 业务字段",升级清晰度
- **`key=request_id`**:既满足顺序约束(Redis 后端写入 payload,Kafka 后端作 partition key),又与原 dedup 逻辑(`md5(request_id+log_type+source)`)对齐
- **`LogDedupHelper.acquire(event_id, app_name)` 用 async context manager**:`__aenter__` 调 `SET NX EX` 返回 bool,`__aexit__` 在异常时 `delete`、正常返回保留 TTL,代替原 `_acquire_dedup` / `_release_dedup` 两套 API
- **`LogQueueService` 保留作为门面**:`enqueue_login_log` / `enqueue_operation_log` 方法签名不变,内部实现替换为 `MessageStreamService.produce`,对 `@Log` 注解零影响
- **`LogAggregatorService` 整类删除**:不留兼容空壳,避免业务方误用;import 失败信号促使迁移彻底
- **`server.py` 的 `_start_background_tasks` 删除 `log_aggregator_task` 行**:`_init_message_stream` 已在 lifespan 中,日志消费者随框架自动拉起;`_stop_background_tasks` 删除对应 cancel
- **`LogConfig` 字段下沉**:8 个纯协议字段全部删除,`log_stream_maxlen` 由 `MessageStreamSettings.message_stream_redis_maxlen` 接管(已存在),只保留 `log_stream_dedup_prefix` / `log_stream_dedup_ttl` / `get_dedup_prefix(app_name)`
- **headers 编解码兼容**:`RedisStreamBackend` 已通过 `_decode_value` 把 fields 拆为 `__value` / `__key` / `__headers`,消费者拿到 `msg.headers` 是 dict,直接读 `event_id` 即可
- **`payload` 类型保持 dict**:`OperLogModel.model_dump(by_alias=True, exclude_none=True)` 已是 dict,`MessageStreamService.produce` 直接接受 dict,框架内编码为 JSON
- **不做"旧消息消费完再切"灰度**:本机环境无生产数据,迁移直接一次切换;线上环境可在切换前手动 `xtrim` 旧 stream 或等待自然过期
- **`LogSanitizer.sanitize_data` 保持调用位置**:`LogQueueService` 推送前脱敏,消费者无需重复,与原行为一致
- **`event_id` 计算位置保持在 `LogQueueService._build_event_id`**:推送端生成,消费端读取,与原行为一致(避免消费端重算导致 key 不一致)

## Risks / Trade-offs

### 风险 1:删除 `LogAggregatorService` 后旧 stream 残留消息
- **风险**:迁移上线时,旧 `log:stream:{app_name}` Stream 可能有未消费的 PEL 消息,直接切换会丢失
- **缓解**:
  - 本机 / 测试环境:`redis-cli DEL log:stream:knowledge-admin log:stream:knowledge-rag` 手动清理,无业务损失
  - 生产环境:切换前 24 小时观察 PEL 长度(`XPENDING log:stream:{app_name} log_aggregator:{app_name}`),确认 PEL 为空再切;或先停 `LogQueueService` 推送 30 秒等老消费跑完再升级
  - 文档明确:本 change 不做"双路并存灰度",运维需配合"消费完旧 stream 再升级"流程

### 风险 2:`LogDedupHelper` 用 async context manager 与原 API 不兼容
- **风险**:任何调用 `_acquire_dedup` / `_release_dedup` 的代码会编译失败
- **缓解**:
  - 这两个方法是 `_` 前缀的私有方法,只在 `LogAggregatorService._process_messages` 内部用过
  - 删除 `LogAggregatorService` 整类时一并消失,无下游影响
  - 新 `LogDedupHelper` 是新 API,业务方按 spec 写消费者即可

### 风险 3:`LogConfig` 8 个字段被删除后其他代码引用爆炸
- **风险**:除了 `log_service.py` 自己,可能有其他文件读 `LogConfig.log_stream_key` 等
- **缓解**:
  - 实施前 `grep -rn "log_stream_key\|log_stream_group\|log_stream_consumer_prefix\|log_stream_batch_size\|log_stream_block_ms\|log_stream_claim_idle_ms\|log_stream_claim_interval_ms\|log_stream_claim_batch_size" --include="*.py"` 全量扫描,确认只在 `log_service.py` 与 `env.py` 内部
  - 任何外部引用一律改用消费者装饰器参数或 `MessageStreamSettings`
  - 若发现 `get_stream_key` / `get_stream_group` 被 `log_annotation.py` 等外部代码引用,先做迁移再删字段

### 风险 4:`server.py` 启动顺序错位导致日志丢失
- **风险**:`_init_message_stream` 在 `_start_background_tasks` 之后调用,但日志消费者依赖 `MessageStreamService.discover_and_start()` 才能开始消费;若启动后立刻有请求触发日志,可能短暂出现"消费者未启动 → 消息堆积"
- **缓解**:
  - 现有 lifespan 顺序已经是 `_start_background_tasks` → `_init_message_stream`,本 change 不调换
  - 框架 `MessageStreamService.produce` 在 `_backend is None` 时抛 `MessageStreamError`,但 `discover_and_start` 完成时 `_backend` 已被注入(`_init_message_stream` 内 `init_from_settings` 第一行),不存在"未 init 就 produce"窗口
  - 短暂的"消息已推送 + 消费者尚未启动"完全由 Redis Stream 的持久化兜底(消息在 stream 中等消费者拉起即可),无丢失风险

### 风险 5:`LogQueueService` 改造后 `LogSanitizer.sanitize_data` 调用位置遗忘
- **风险**:推送前脱敏 → 推送后未脱敏,可能把敏感数据写到 Redis Stream 中
- **缓解**:
  - 实现时严格保持 `sanitize_data` 在 `enqueue_*` 内部调用、`produce` 之前
  - 单元测试覆盖"推送前 payload 不含 password 字段"

### 风险 6:测试环境无 Redis 时端到端测试卡死
- **风险**:`test_log_aggregation_via_message_stream.py` 需要真实 Redis 跑端到端
- **缓解**:
  - 复用 `test_message_stream.py` 的"6379 端口未连通自动 skip"策略,本地无 Redis 时 skip 而非 fail
  - CI 环境配 docker-compose Redis 服务,保证集成测试可跑

## Migration Plan

### 阶段 1:`LogDedupHelper` 与业务消费者(0.5 天)
- 新建 `knowledge_common/service/log_service.py` 中的 `LogDedupHelper` 类(async context manager)
- 新建 `knowledge_common/message/consumer/log_consumer.py`:单文件含 4 个消费函数
  - `@consumer(topic='log:login:knowledge-admin', group_id='log_writer:knowledge-admin')` 装饰 `handle_admin_login_log`
  - `@consumer(topic='log:operation:knowledge-admin', group_id='log_writer:knowledge-admin')` 装饰 `handle_admin_operation_log`
  - `@consumer(topic='log:login:knowledge-rag', group_id='log_writer:knowledge-rag')` 装饰 `handle_rag_login_log`
  - `@consumer(topic='log:operation:knowledge-rag', group_id='log_writer:knowledge-rag')` 装饰 `handle_rag_operation_log`
- 消费者函数体:`async with LogDedupHelper.acquire(event_id, app_name) as ok: if not ok: return; async with AsyncSessionLocal() as session: dao.add(...); await session.commit()`,其中 `app_name` 从 `msg.headers['app_name']` 读取(`LogQueueService` 推送时写入),`dao` 走 `knowledge_common.dao` 下按 `app_name` 分流到对应表
- 4 个消费函数在 admin / rag 任一进程启动时都会被 import + 装饰器注册(因默认扫描路径包含 `knowledge_common.message.consumer`),各自拉起 4 个消费协程 + 4 个 idle 接管协程;但因 topic 按 `app_name` 隔离,非本 app 的 2 个消费者会长期空转阻塞拉取(默认 2s block_ms),CPU/网络开销可忽略,且复用同一 Redis 连接;有意保留"声明式纯粹性",不在装饰器层引入运行时 app_name 条件分支

### 阶段 2:`LogQueueService` 切到 `MessageStreamService.produce`(0.5 天)
- `_xadd_event` 删除
- `enqueue_login_log` / `enqueue_operation_log` 改:计算 `event_id` → `payload = LogSanitizer.sanitize_data(...)` → `headers = {'event_id': ..., 'event_type': ..., 'trace_id': ..., 'span_id': ..., 'app_name': ..., 'source': ...}` → `await MessageStreamService.produce(topic=f'log:{event_type}:{app_name}', value=payload, key=request_id, headers=headers)`
- `_resolve_app_name` 保留(仍需要从 request.app.state 取)

### 阶段 3:删除 `LogAggregatorService` + `LogConfig` 精简(0.5 天)
- `LogAggregatorService` 整类删除
- `LogConfig` 删除 `log_stream_key` / `log_stream_group` / `log_stream_consumer_prefix` / `log_stream_batch_size` / `log_stream_block_ms` / `log_stream_claim_idle_ms` / `log_stream_claim_interval_ms` / `log_stream_claim_batch_size` 共 8 个字段
- `LogConfig.log_stream_maxlen` 删除(由 `MessageStreamSettings.message_stream_redis_maxlen` 接管)
- `LogConfig.get_stream_key` / `get_stream_group` 删除(不再有用)
- 保留:`log_stream_dedup_prefix` / `log_stream_dedup_ttl` / `get_dedup_prefix(app_name)`

### 阶段 4:`server.py` 后台任务清理(0.25 天)
- admin / rag 的 `_start_background_tasks` 删除 `app.state.log_aggregator_task = asyncio.create_task(LogAggregatorService.consume_stream(...))` 这两行
- admin / rag 的 `_stop_background_tasks` 删除对应的 `log_task = getattr(app.state, 'log_aggregator_task', None); if log_task: log_task.cancel()` 块
- import 同步清理:删除 `from knowledge_common.service.log_service import LogAggregatorService`

### 阶段 5:测试与文档(0.5 天)
- 新增 `knowledge-common/tests/test_log_aggregation_via_message_stream.py`,模拟 push → consume → 去重 → 落库,断言数据库表行为
- 重写 `docs/rag/log-aggregator-flow.md`,Mermaid 时序图从"裸 xadd → xreadgroup"升级为"produce → consumer 装饰器 → 落库"
- 在 `knowledge-common/README.md` 消息流服务章节增加"日志聚合接入示例"

### 回滚策略
- 如发现新消费者落库行为有偏差:把 `LogAggregatorService` 从 git 历史恢复,`server.py` 恢复 `log_aggregator_task`,`LogConfig` 字段恢复,新消费者文件改名 `.py.bak` 不再被装饰器扫描;由于 `MessageStreamService` 仍是新框架,旧路径与新框架可短期共存
- 但本 change 倾向"一次性切换 + 测试覆盖充分",回滚作为最后兜底

## Open Questions

1. **`LogQueueService._build_event_id` 是否要改放到 headers 计算 helper?**
   - 倾向:不改,保持 `LogQueueService` 内部静态方法,只在推送端用
   - 待定:若 RAG 端业务需要类似 `event_id` 计算,再抽 helper

2. **消费者函数名是否要带 `_handler` 后缀?**
   - 候选:`handle_operation_log` / `handle_login_log`
   - 候选:`operation_log_consumer` / `login_log_consumer`
   - 倾向:`handle_operation_log` / `handle_login_log`,与 message_stream 模块文档示例的 `handle` 风格对齐

3. **`LogDedupHelper` 是否要支持自定义 TTL?**
   - 倾向:从 `LogConfig.log_stream_dedup_ttl` 取默认值,不暴露参数,后续需要再扩
   - 待定:若有"短 TTL 业务"场景,再加可选参数

4. **是否在 `MessageStreamService.produce` 失败时降级写日志文件?**
   - 倾向:不降级,直接抛 `MessageStreamError`(对 `LogQueueService.enqueue_*` 调用方透明,由 `@Log` 注解侧 try/except 决定)
   - 待定:若运维强烈要求"日志推送失败要写本地文件兜底",再加降级路径

5. **`test_log_aggregation_via_message_stream.py` 是否要覆盖 admin/rag 同时跑?**
   - 倾向:单元测试只覆盖单 app(admin)的 topic 隔离行为,跨 app 隔离由 spec 场景描述兜底
   - 待定:若发现跨 app 串扰风险,再加端到端跨 app 测试

6. **是否要把 `log_consumer.py` 的两个消费函数合并为一个?**
   - 候选:一个 `handle_log` 函数,内部按 `headers['event_type']` 分发到 dao
   - 候选:两个独立函数,分别订阅 login / operation topic
   - 倾向:两个独立函数,topic 命名与消费组隔离更清晰,扩展性好(以后可单独加 trace 日志消费者)
