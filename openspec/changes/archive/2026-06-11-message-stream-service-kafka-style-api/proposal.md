## Why

当前项目里 Redis Stream 的协议操作(XADD/XREADGROUP/XACK/XAUTOCLAIM)与日志业务强耦合在 `log_service.py` 一个文件里,后续 RAG 端要做长流程的"文档解析+文档拆分"任务时(分钟级、5 步骤、强可观测性需求),这套裸调用的方式既无法复用也无法演进。需要在 `knowledge-common` 沉淀一个**业务可用的消息流服务**,让业务层用声明式的 @consumer 装饰器声明消费点、用 produce 推送消息,并保证未来切到 Kafka 时**业务层、装饰器、门面 API、消息结构全部零修改**,只换底层后端实现即可。

## What Changes

- **新增 `MessageStreamService`**:服务层门面,提供 `produce` / `discover_and_start` / `shutdown` 等生命周期方法。
- **新增 `@consumer` 装饰器**(独立文件 `consumer.py`):业务方用 `@consumer(topic, group_id, ...)` 声明消费点,启动时全路径扫描,自动拉起消费协程。
- **新增 `Message` 数据类**:字段对齐 Kafka(topic / key / value / headers / offset / partition),保证切 Kafka 时零字段调整。
- **新增 `StreamBackend` 抽象接口**:定义 6 个核心方法(publish/consume/ack/create_group/claim_idle/shutdown),藏住 Redis Stream 与 Kafka 的协议差异。
- **新增 `RedisStreamBackend`**:基于 redis.asyncio 实现当前后端,支撑日志聚合场景。
- **新增 `KafkaStreamBackend`**:基于 confluent-kafka-python 2.14+(`confluent_kafka.aio.AIOProducer` / `AIOConsumer` 异步包装)实现,与 Redis 后端共享 `StreamBackend` 6 个方法契约,业务层零感知。
- **新增 `MessageStreamSettings` Pydantic 配置类**:统一管理后端选择(`MESSAGE_STREAM_BACKEND=redis|kafka`)、Redis 后端参数(MAXLEN)、Kafka 后端参数(bootstrap.servers / SASL / SSL / acks / linger.ms / partitions / replication.factor 等),共 20 个配置字段。
- **新增 `create_backend(settings, redis)` 工厂函数**:按配置选择 `RedisStreamBackend` / `KafkaStreamBackend` 实例,Redis 后端需注入 redis 客户端,未知后端类型抛 `MessageStreamError`。
- **新增 `MessageStreamService.init_from_settings(settings, *, redis)` 类方法**:lifespan 一行注入,内部调 `create_backend` + `init`,返回后端实例;替换原"硬编码 `MessageStreamService.init(RedisStreamBackend(...))`"范式,实现"切后端只改 .env 即可,业务零修改"。
- **5 个 .env 文件(.env.dev / .env.prod / .env.dockermy / .env.dockerpg + knowledge-rag)统一追加 20 个 `MESSAGE_STREAM_*` 字段**,并按部署环境给出合理默认值(开发环境用 redis / 演示用 kafka 备好 SASL+SSL 全套字段模板)。
- **新增 `MessageStreamError` 异常类**:统一异常体系,业务层 try/except 一次。
- **新增业务方路径注册 API**:`register_consumer_paths(paths)` 接收业务方声明的消费者所在包路径,框架按需 import 扫描,不对齐"框架硬编码全路径扫描"。
- **推送重试**:`produce` 默认重试 3 次,业务方可定制 `max_retries` / `retry_interval`;失败最终抛 `MessageStreamError`,业务方自行决定后续处理。
- **消费层透明化**:业务层不感知 ack、消息拉取、分发、重试接管(由后端协议兜底:Stream 是 PEL 接管,Kafka 是 offset 重平衡)。
- **新增 `MessageStreamService` 配套的 lifespan 注入范式**:对齐现有 `auto_register_routers` 业务方声明路径模式。

## Capabilities

### New Capabilities

- `message-stream-service`:消息流服务整体能力,涵盖装饰器定义、门面 API、消息结构、注册机制、抽象后端、Kafka 兼容字段约定、推送重试、消费层透明化约定等。

### Modified Capabilities

(无 — 现有 `annotated-transaction` / `config-auto-discovery` / `job-app-scope-isolation` 三个 spec 的需求均无变化,本次为新增能力)

## Impact

- **新增代码**(knowledge-common)
  - `knowledge_common/message_stream/__init__.py`(统一导出)
  - `knowledge_common/message_stream/consumer.py`(@consumer 装饰器)
  - `knowledge_common/message_stream/service.py`(MessageStreamService 门面)
  - `knowledge_common/message_stream/message.py`(Message 数据类)
  - `knowledge_common/message_stream/exceptions.py`(MessageStreamError)
  - `knowledge_common/message_stream/backends/base.py`(StreamBackend 抽象)
  - `knowledge_common/message_stream/backends/redis_stream.py`(RedisStreamBackend)
- **后续 change**(不在本 change 范围)
  - 日志模块改造用新服务:本 change 不做,作为下一 change 落地
  - 业务状态表(rag.task):本 change 不做,业务状态由各业务按需设计
  - 文档处理业务编排:本 change 不做
- **本 change 已落地**(对照原 design.md 阶段 3)
  - ✅ `backends/kafka_stream.py:KafkaStreamBackend` — 切 Kafka 的实现已交付,业务侧零修改
  - ✅ `.env` 一行切换:`MESSAGE_STREAM_BACKEND=redis|kafka`
  - ✅ confluent-kafka-python>=2.5.0 已纳入 `knowledge-common/pyproject.toml`
  - 后续如需引入 SASL/SSL 真集群联调 / 集成测试(testcontainers)等,另起 change
- **依赖**
  - 当前:redis.asyncio(已用)+ confluent-kafka>=2.5.0(新增,提供 AIOProducer/AIOConsumer)
  - 客户端选型说明:confluent-kafka 内部走 librdkafka(C 库),`confluent_kafka.aio` 模块在 2.5 起稳定,提供线程池包装的 awaitable 接口;与 FastAPI 异步生态兼容
- **风险**
  - 装饰器 + 全路径 import 副作用:业务模块 import 顺序需在 lifespan 启动前确定
  - 业务方忘记调 `register_consumer_paths` → 消费者未注册,需在 lifespan 中加显式提示
  - 切 Kafka 时若业务层用了消息 ID(Stream 格式 1234-0),需提前用业务 ID 替换(本 change 通过 Message 字段约定 + 装饰器 business_id_fn 强制业务自管)
