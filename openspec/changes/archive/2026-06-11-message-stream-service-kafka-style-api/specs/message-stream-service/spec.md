## ADDED Requirements

### Requirement: 消息流服务门面

系统 SHALL 提供 `MessageStreamService` 类作为消息流服务门面,放在 `knowledge_common/message_stream/` 子包内。门面 SHALL 提供 `produce` / `register_consumer_paths` / `discover_and_start` / `shutdown` 等类方法,且 SHALL 不以 `Redis` / `Kafka` 等中间件名开头(保证切后端时门面零修改)。

#### Scenario: 业务方调用 produce 推送消息
- **WHEN** 业务代码调用 `await MessageStreamService.produce(topic="x", value={"k": "v"}, key="k1")`
- **THEN** 消息 SHALL 被提交到指定 topic,方法返回消息 ID

#### Scenario: 切后端时门面 API 零修改
- **WHEN** 后端从 RedisStreamBackend 切换为 KafkaStreamBackend(通过 .env 配置)
- **THEN** 业务层调用的 `MessageStreamService.produce(...)` SHALL 保持原签名与方法名,业务代码零修改

### Requirement: @consumer 装饰器

系统 SHALL 提供 `@consumer` 装饰器,放在独立文件 `knowledge_common/message_stream/consumer.py` 中。装饰器 SHALL 接收 `topic`(必填,字符串)、`group_id`(必填,字符串)、`id`(可选,默认用函数名)、`business_id_fn`(可选,返回业务幂等键)、`on_error`(可选,默认 `retry`)、`max_retries`(可选,默认 `3`)等参数。装饰器 SHALL 把函数注册到 `MessageStreamService` 的消费者表中,业务方不需要手动调注册方法。

#### Scenario: 业务方声明消费者
- **WHEN** 业务代码在任意模块的顶层定义 `@consumer(topic="log:op", group_id="log_writer")` 装饰的 async 函数
- **THEN** 该函数 SHALL 在框架 `discover_and_start` 时被自动发现并拉起后台消费协程

#### Scenario: 装饰器参数对齐 Kafka
- **WHEN** 切后端为 Kafka 时
- **THEN** 装饰器参数名 `topic` / `group_id` SHALL 与 Kafka 客户端原生参数一致(切 Kafka 时装饰器零修改)

### Requirement: produce 推送方法

`MessageStreamService.produce` SHALL 是异步方法,签名 SHALL 为 `produce(topic, value, key=None, headers=None, max_retries=3, retry_interval=0.5) -> str`。方法名 SHALL 固定为 `produce`(对齐 confluent-kafka),且 SHALL 在重试 `max_retries` 次后仍未成功时抛出 `MessageStreamError`。

#### Scenario: 推送成功
- **WHEN** 业务调用 `produce(topic, value)`
- **THEN** 方法 SHALL 在一次或多次重试内成功投递,返回消息 ID,正常返回

#### Scenario: 推送失败抛异常
- **WHEN** 业务调用 `produce(topic, value, max_retries=3)` 且三次均失败
- **THEN** 方法 SHALL 抛出 `MessageStreamError`,业务方 SHALL 通过 `try/except` 决定后续处理(告警 / 落失败表 / 丢弃 / 重投)

#### Scenario: 业务定制重试
- **WHEN** 业务调用 `produce(topic, value, max_retries=5, retry_interval=1.0)`
- **THEN** 方法 SHALL 用业务定制的重试次数和间隔,默认值 SHALL 不生效

### Requirement: Message 消息结构

`Message` 数据类 SHALL 包含以下字段(命名对齐 Kafka):`topic: str`、`key: str | None`、`value: Any`、`headers: dict`(默认 `{}`)、`timestamp: int`、`offset: str`、`partition: int | None`(Stream 无分区,值为 `None`)。为平滑过渡,Message SHALL 同时提供 `stream` / `payload` 属性别名(分别返回 `topic` / `value`)。

#### Scenario: 业务层读消息字段
- **WHEN** 业务函数收到 `msg: Message`
- **THEN** 业务 SHALL 通过 `msg.value` 读载荷、`msg.key` 读业务键、`msg.topic` 读主题

#### Scenario: 切后端时字段零调整
- **WHEN** 后端从 Redis 切到 Kafka
- **THEN** Message 字段名 SHALL 保持不变,业务层读消息代码 SHALL 零修改

#### Scenario: 旧名别名兼容
- **WHEN** 业务代码读 `msg.stream` 或 `msg.payload`
- **THEN** SHALL 等价于 `msg.topic` 或 `msg.value`(平滑过渡,老代码无需立刻迁移)

### Requirement: StreamBackend 抽象后端

`StreamBackend` 抽象接口 SHALL 定义 6 个方法:`publish(topic, value, key, headers) -> str`、`consume(topic, group_id, consumer_id, block_ms, count) -> list[Message]`、`ack(topic, group_id, *msg_offsets) -> int`、`create_group(topic, group_id) -> None`、`claim_idle(topic, group_id, consumer_id, min_idle_ms) -> list[Message]`、`shutdown() -> None`。后端实现 SHALL 藏住 Redis Stream 与 Kafka 的协议差异。

#### Scenario: RedisStreamBackend 实现 publish
- **WHEN** 业务通过 `MessageStreamService.produce` 触发 `RedisStreamBackend.publish`
- **THEN** 后端 SHALL 内部调用 redis.asyncio 的 xadd 接口,适配 Message 字段(Stream xid → Message.offset,fields 拆为 headers + value)

#### Scenario: 切到 Kafka 后端
- **WHEN** .env 配置 `MESSAGE_STREAM_BACKEND=kafka`,框架加载 `KafkaStreamBackend`
- **THEN** 同一个 `StreamBackend` 接口 SHALL 由 confluent-kafka-python 2.14+(`confluent_kafka.aio.AIOProducer` / `AIOConsumer`)实现,`AdminClient` 通过 `asyncio.to_thread` 包装避免阻塞事件循环;业务层 SHALL 无感知
- **AND** 切换 SHALL 只需改 .env 一行,装饰器 / `produce` / `Message` / 异常类型全部保持不变

### Requirement: 配置驱动后端选择

系统 SHALL 提供 `MessageStreamSettings` Pydantic 配置类(放在 `knowledge_common/config/env.py`),统一管理后端选择与跨后端参数,字段全部从 .env 读取。

#### Scenario: 默认走 Redis 后端
- **WHEN** .env 未设置 `MESSAGE_STREAM_BACKEND`
- **THEN** 框架 SHALL 加载 `RedisStreamBackend`,保持现有行为不变

#### Scenario: 切 Kafka 后端
- **WHEN** .env 设置 `MESSAGE_STREAM_BACKEND=kafka`
- **THEN** 框架 SHALL 加载 `KafkaStreamBackend`,该后端用 confluent-kafka-python 实现

#### Scenario: 未知的后端类型被拦截
- **WHEN** .env 设置 `MESSAGE_STREAM_BACKEND=other`(不在 `Literal['redis', 'kafka']` 范围内)
- **THEN** Pydantic SHALL 在启动期报校验错误,避免运行期才发现后端不可用

### Requirement: create_backend 工厂

`backends/factory.py` SHALL 提供 `create_backend(settings, *, redis=None) -> StreamBackend` 工厂函数,按 `settings.message_stream_backend` 返回对应后端实例。

#### Scenario: Redis 后端创建
- **WHEN** 调用 `create_backend(settings, redis=app.state.redis)` 且 settings 后端为 `redis`
- **THEN** 函数 SHALL 返回 `RedisStreamBackend(redis, maxlen=settings.message_stream_redis_maxlen)` 实例

#### Scenario: Redis 后端缺客户端
- **WHEN** 调用 `create_backend(settings)` 且 settings 后端为 `redis` 且未传 `redis` 参数
- **THEN** 函数 SHALL 抛出 `MessageStreamError`,提示"Redis 后端需注入 redis 客户端"

#### Scenario: Kafka 后端创建
- **WHEN** 调用 `create_backend(settings, redis=None)` 且 settings 后端为 `kafka`
- **THEN** 函数 SHALL 返回 `KafkaStreamBackend` 实例,参数从 `settings.message_stream_kafka_*` 字段读取(bootstrap_servers / client_id / security_protocol / sasl_mechanism / sasl_username / sasl_password / acks / linger_ms / request_timeout_ms / session_timeout_ms / heartbeat_interval_ms / auto_offset_reset / create_topic_partitions / create_topic_replication_factor)

#### Scenario: 未知后端类型
- **WHEN** `settings.message_stream_backend` 不在 `Literal['redis', 'kafka']` 范围内
- **THEN** 函数 SHALL 抛出 `MessageStreamError`,提示后端类型未知

### Requirement: init_from_settings 初始化入口

`MessageStreamService` SHALL 提供 `init_from_settings(settings, *, redis=None) -> StreamBackend` 类方法,lifespan 中一行调用即可完成"加载配置 → 创建后端 → 注入门面"三件事。

#### Scenario: lifespan 一行调用
- **WHEN** 业务方在 lifespan 中调 `MessageStreamService.init_from_settings(MessageStreamConfig, redis=app.state.redis)`
- **THEN** 方法 SHALL 内部调 `create_backend(settings, redis=redis)` 创建后端,再调 `init(backend)` 注入门面,并返回后端实例供业务方选择使用

#### Scenario: 业务代码零修改切后端
- **WHEN** .env 从 `MESSAGE_STREAM_BACKEND=redis` 改为 `MESSAGE_STREAM_BACKEND=kafka`
- **THEN** lifespan 调用代码 SHALL 不变,业务推送/消费代码 SHALL 不变,只需 .env 切换即可使用不同后端

### Requirement: 业务方路径注册

`MessageStreamService` SHALL 提供 `register_consumer_paths(paths: list[str])` 类方法,接收业务方声明的消费者所在 Python 包路径(如 `['knowledge_admin.service', 'knowledge_content.service']`)。框架 SHALL 不硬编码全项目路径扫描,各子项目在 lifespan 中主动声明。

#### Scenario: 业务方声明路径
- **WHEN** 子项目 lifespan 调 `MessageStreamService.register_consumer_paths(['knowledge_admin.service'])`
- **THEN** 框架 SHALL 在 `discover_and_start` 时只扫描该路径下的模块,不扫描其他路径

#### Scenario: 多个子项目分别声明
- **WHEN** admin 和 rag 各自 lifespan 调 `register_consumer_paths`,传递各自的 service 路径
- **THEN** 框架 SHALL 累加所有声明的路径,统一扫描(同进程场景)

#### Scenario: 业务方忘记调用
- **WHEN** 业务方 lifespan 未调 `register_consumer_paths`
- **THEN** `discover_and_start` SHALL 打印警告日志,启动 0 个消费者(开发模式);生产模式 SHALL 抛异常

### Requirement: discover_and_start 自动扫描与启动

`MessageStreamService.discover_and_start()` SHALL 主动 import 业务方声明的每个路径下的所有模块,触发 `@consumer` 装饰器注册,再为每个已注册的消费者拉起后台消费协程。扫描 SHALL 递归处理子包,且 SHALL 对装饰器注册做去重保护(同一函数不重复注册)。

#### Scenario: 启动时扫描
- **WHEN** `discover_and_start` 被调用
- **THEN** 框架 SHALL 反射 import 所有声明路径下的模块,装饰器把函数注册到 `_consumers` 表,后台协程被拉起

#### Scenario: 重复启动去重
- **WHEN** 同一函数被装饰两次(测试场景)或同一路径被多次注册
- **THEN** 框架 SHALL 跳过重复项,不抛异常

#### Scenario: reset 方法用于测试
- **WHEN** 单元测试需要清理状态
- **THEN** 业务方 SHALL 调 `MessageStreamService.reset()` 清空所有状态

### Requirement: shutdown 关闭钩子

`MessageStreamService.shutdown()` SHALL 取消所有后台消费协程、关闭后端连接、清理任务表,且 SHALL 在 FastAPI lifespan 退出阶段被调用。

#### Scenario: 正常关闭
- **WHEN** 应用退出时 lifespan 调 `await MessageStreamService.shutdown()`
- **THEN** 所有消费协程 SHALL 收到取消信号并优雅退出,后端连接 SHALL 关闭

### Requirement: 业务层职责边界

业务层 SHALL 只通过 `await MessageStreamService.produce(...)` 推送消息,通过 `@consumer(topic, group_id, ...)` 装饰的 `async def handle(msg: Message) -> None` 消费消息。业务层 SHALL 不感知消息拉取循环、不感知 ack 调用、不感知消费组协调、不感知卡住消息接管。所有这些基础设施细节 SHALL 由 `MessageStreamService` 与后端协议(Stream 是 PEL 接管 / Kafka 是 offset 重平衡)兜底。

#### Scenario: 业务抛异常自动不 ack
- **WHEN** 业务消费函数执行时抛异常
- **THEN** 框架 SHALL 捕获异常,不调用 ack,后端协议 SHALL 决定下一步(Stream 是超时被其他 worker 接管 / Kafka 是重平衡后重读)

#### Scenario: 业务正常返回自动 ack
- **WHEN** 业务消费函数正常返回
- **THEN** 框架 SHALL 自动调用 ack,消息从待确认列表移除,业务 SHALL 不感知 ack 调用

### Requirement: 推送失败统一异常

`MessageStreamError` SHALL 是消息流服务所有可恢复错误的统一异常基类,放在 `knowledge_common/message_stream/exceptions.py`。`produce` 在推送失败重试用完时 SHALL 抛出 `MessageStreamError`,业务方 SHALL 通过 `try/except MessageStreamError as e` 统一处理。

#### Scenario: 业务捕获推送失败
- **WHEN** 业务 `try: await produce(...) except MessageStreamError as e: ...`
- **THEN** 业务 SHALL 能捕获所有推送失败情况,无需分别处理 Stream / Kafka / 后端具体异常类型

### Requirement: 切 Kafka 零返工的 4 个埋点

消息流服务 SHALL 在第一版实现时即贯彻以下 4 个埋点,确保切 Kafka 时业务代码零修改:1) 业务层 SHALL 用业务 ID(`business_id_fn` 装饰器参数或 `msg.key`)做幂等键,不依赖消息 ID(Stream 的 xid / Kafka 的 offset);2) 顺序保证 SHALL 通过 `key` 参数声明,后端各自实现(Stream 把 key 塞 payload / Kafka 把 key 作为 partition key);3) 异常语义 SHALL 统一(业务抛 = 失败 = 框架不 ack = 后端协议兜底);4) 业务状态 SHALL 由各业务系统(关系库)自己维护,消息层不持有业务状态。

#### Scenario: 业务幂等键不依赖消息 ID
- **WHEN** 业务方用 `@consumer(topic, group_id, business_id_fn=lambda msg: msg.value["doc_id"])` 声明幂等键
- **THEN** 切 Kafka 时该业务幂等逻辑 SHALL 保持不变,无需任何调整

#### Scenario: 顺序保证通过 key 参数声明
- **WHEN** 业务方 `produce(topic, value, key="doc_123")` 声明业务键
- **THEN** RedisStreamBackend 把 key 写入消息 payload 供业务按 key 过滤,KafkaStreamBackend 把 key 作为 partition key 保证同 key 顺序处理

#### Scenario: 切 Kafka 时业务状态表不受影响
- **WHEN** 业务方在关系库维护 `task` 状态表(与消息中间件解耦)
- **THEN** 切 Kafka 时业务状态表 SHALL 零修改,业务层 SHALL 继续用原表结构读写状态
