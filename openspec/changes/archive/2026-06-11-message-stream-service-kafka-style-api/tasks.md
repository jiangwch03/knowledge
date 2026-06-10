## 1. 模块骨架搭建

- [x] 1.1 在 `knowledge-common/src/knowledge_common/` 下创建 `message_stream/` 子包,含 `__init__.py` 占位文件
- [x] 1.2 创建 `exceptions.py`,定义 `MessageStreamError` 异常基类(继承自 `Exception`,带 topic / cause 等上下文属性)
- [x] 1.3 创建 `message.py`,定义 `Message` 数据类(topic / key / value / headers / timestamp / offset / partition 字段,带 `stream` / `payload` 属性别名)
- [x] 1.4 完善 `__init__.py`,统一导出 `MessageStreamService` / `consumer` / `Message` / `MessageStreamError`
- [x] 1.5 在 `knowledge-common/pyproject.toml` 确认 redis.asyncio 依赖已声明(无需新增)

## 2. StreamBackend 抽象接口

- [x] 2.1 创建 `backends/__init__.py` 与 `backends/base.py`,定义 `StreamBackend` 抽象基类(ABC)
- [x] 2.2 声明 6 个抽象方法:`publish` / `consume` / `ack` / `create_group` / `claim_idle` / `shutdown`,带类型签名
- [x] 2.3 编写抽象接口的 docstring,说明每个方法的语义、参数约束、异常约定

## 3. RedisStreamBackend 实现

- [x] 3.1 创建 `backends/redis_stream.py`,实现 `RedisStreamBackend(StreamBackend)` 类,构造函数接收 `redis: aioredis.Redis`
- [x] 3.2 实现 `publish(topic, value, key, headers)`:内部调 `xadd`,处理 `maxlen` 近似裁剪,适配 Message 字段(value dict 拆 `__value` / `__key` / `__headers` 三段)
- [x] 3.3 实现 `consume(topic, group_id, consumer_id, block_ms, count)`:内部调 `xreadgroup COUNT N BLOCK ms`,反序列化消息为 `Message` 对象
- [x] 3.4 实现 `ack(topic, group_id, *msg_offsets)`:内部调 `xack`,处理空偏移量
- [x] 3.5 实现 `create_group(topic, group_id)`:内部调 `xgroup_create MKSTREAM`,捕获 `BUSYGROUP` 异常做幂等
- [x] 3.6 实现 `claim_idle(topic, group_id, consumer_id, min_idle_ms)`:内部调 `xautoclaim` 接管卡住消息
- [x] 3.7 实现 `shutdown`:清理客户端引用(不主动关闭,redis 连接由 RedisContext 统一管理)
- [x] 3.8 编写 Message ↔ Redis Stream 字段映射的单元测试(头部 / 业务键 / offset 转换) — 留给第 7 节

## 4. @consumer 装饰器

- [x] 4.1 创建 `consumer.py`,定义 `consumer(topic, group_id, id=None, business_id_fn=None, on_error="retry", max_retries=3)` 装饰器工厂
- [x] 4.2 装饰器内部把 `(consumer_id, topic, group_id, handler, business_id_fn, on_error, max_retries)` 写入 `MessageStreamService._consumers` 表
- [x] 4.3 实现注册去重:同一 `(模块路径, 函数名)` 只注册一次,重复装饰跳过
- [x] 4.4 编写装饰器单元测试(基本注册、参数传递、去重) — 留给第 7 节

## 5. MessageStreamService 门面

- [x] 5.1 创建 `service.py`,定义 `MessageStreamService` 类(全 @classmethod,不实例化)
- [x] 5.2 实现类变量:`_backend: StreamBackend | None`、`_consumers: dict[str, ConsumerInfo]`、`_tasks: dict[str, asyncio.Task]`、`_scan_paths: list[str]`
- [x] 5.3 实现 `init(backend)`:注入后端实现,记录日志
- [x] 5.4 实现 `register_consumer_paths(paths)`:累加业务方声明的路径(自动去重),记录日志
- [x] 5.5 实现 `discover_and_start()`:用 `importlib` + `pkgutil.iter_modules` 扫描所有声明路径,反射 import 触发装饰器注册,再为每个 consumer 拉起后台协程
- [x] 5.6 实现 `_start_consumer(consumer_info)`:拉起后台消费协程(双层 `while True` 循环,内层调 `consume`,业务函数返回成功则 `ack`,异常则不 `ack` 由后端兜底)
- [x] 5.7 实现 `produce(topic, value, key=None, headers=None, max_retries=3, retry_interval=0.5)`:调 `_backend.publish` 失败时按 `retry_interval` 退避重试,重试用完抛 `MessageStreamError`
- [x] 5.8 实现 `shutdown()`:取消所有 `_tasks`、调 `_backend.shutdown`、清理状态
- [x] 5.9 实现 `reset()`:清空所有类变量,供单元测试用
- [x] 5.10 编写异常处理:连接异常 / 超时 / 业务异常分别 log,保证协程不退出
- [x] 5.11 编写 `_consume_loop` 内部协程的单元测试(成功 / 失败 / 卡住场景) — 留给第 7 节

## 6. 业务方接入验证

- [x] 6.1 在 `knowledge-admin/src/knowledge_admin/server/server.py` 的 lifespan 中加入 `MessageStreamService` 初始化(暂不迁移日志消费者,只验证接入范式)
- [x] 6.2 编写端到端测试:admin 启动 → 调 `produce("test:topic", {"k": "v"})` → 装饰器消费者收到 → 验证 ack 行为
- [x] 6.3 验证 `shutdown` 优雅退出(无未取消协程残留)
- [x] 6.4 验证 `reset` 行为(测试可多次跑)
- [x] 6.5 验证重试行为(故意把后端调成失败,确认 3 次后抛 `MessageStreamError`)

## 7. 单元测试

- [x] 7.1 `Message` 数据类单元测试(字段访问、别名兼容、默认值)
- [x] 7.2 `MessageStreamError` 单元测试(异常信息、上下文属性)
- [x] 7.3 `RedisStreamBackend` 单元测试(`fakeredis` 或真 redis,覆盖 6 个方法)
- [x] 7.4 `@consumer` 装饰器单元测试(注册、去重、参数透传)
- [x] 7.5 `MessageStreamService.produce` 单元测试(成功 / 重试 / 最终失败抛异常)
- [x] 7.6 `MessageStreamService.discover_and_start` 单元测试(模拟声明路径 + 模拟装饰器注册)
- [x] 7.7 端到端集成测试(模拟一个业务函数 + 真 Redis,验证 produce → consume → ack 全链路)

## 8. 文档

- [x] 8.1 在 `knowledge-common/README.md` 增加"消息流服务"章节,展示装饰器使用范式与 lifespan 注入流程
- [x] 8.2 在 `docs/rag/` 下创建 `message-stream-service-design.md`,业务化描述"消息流服务"的设计与"切 Kafka 零修改"承诺
- [x] 8.3 文档列出"切 Kafka 的 4 个埋点"(业务 ID 自管 / 幂等键业务声明 / 顺序用 key 参数 / 异常语义统一),作为后续 change 的执行清单
- [x] 8.4 文档说明与 `RedisPubSubUtil` 的对仗关系(命名 / 位置 / 职责差异)

## 9. 配置驱动后端切换(同 change 增补,实现"切后端只改 .env")

- [x] 9.1 在 `knowledge_common/config/env.py` 新增 `MessageStreamSettings` Pydantic 配置类,字段含:`message_stream_backend: Literal['redis', 'kafka']` + 4 个跨后端公共消费参数 + 1 个 Redis MAXLEN + 14 个 Kafka 全量参数(bootstrap_servers / client_id / security_protocol / sasl_mechanism / sasl_username / sasl_password / acks / linger_ms / request_timeout_ms / session_timeout_ms / heartbeat_interval_ms / auto_offset_reset / create_topic_partitions / create_topic_replication_factor),共 20 个字段
- [x] 9.2 `MessageStreamSettings` 提供 `is_kafka` / `is_redis` 计算属性,供业务代码选择性使用
- [x] 9.3 在 `GetConfig` 中增 `get_message_stream_config()` 方法 + `MessageStreamConfig = get_config.get_message_stream_config()` 全局实例
- [x] 9.4 创建 `backends/factory.py`,实现 `create_backend(settings, *, redis=None) -> StreamBackend` 工厂函数:按 settings 后端字段返回 `RedisStreamBackend` / `KafkaStreamBackend`,未知后端类型抛 `MessageStreamError`
- [x] 9.5 `create_backend` 内部用局部 import(`from ... import RedisStreamBackend / KafkaStreamBackend`)避免启动期循环依赖
- [x] 9.6 `MessageStreamService` 增 `init_from_settings(settings, *, redis=None) -> StreamBackend` 类方法,内部调 `create_backend` + `init`,返回后端实例
- [x] 9.7 `init_from_settings` docstring 列出 lifespan 调用范式,提供"切后端只改 .env"零修改承诺的文档证据
- [x] 9.8 5 个 .env 文件(`knowledge-admin/.env.dev` / `.env.prod` / `.env.dockermy` / `.env.dockerpg` + `knowledge-rag/.env.dev`)统一追加 20 个 `MESSAGE_STREAM_*` 字段,中文注释说明每个字段含义与取值范围
- [x] 9.9 `knowledge-admin/src/knowledge_admin/server/server.py` 与 `knowledge-rag/src/knowledge_rag/server/server.py` 的 lifespan 中将原有 `MessageStreamService.init(RedisStreamBackend(...))` 硬编码范式替换为 `MessageStreamService.init_from_settings(MessageStreamConfig, redis=app.state.redis)`,业务零修改
- [x] 9.10 补充文档:`docs/rag/message-stream-service-design.md` 增“运行时流程全景”章节,描述 lifespan init / produce / consume / shutdown 四个阶段的后端选择路径

## 10. KafkaStreamBackend 实现(confluent-kafka)

- [x] 10.1 选型决策:confluent-kafka-python 2.14+(`confluent_kafka.aio.AIOProducer` / `AIOConsumer`),librdkafka C 库 + 内部 ThreadPoolExecutor 包装提供 awaitable 接口
- [x] 10.2 `pyproject.toml` 追加 `confluent-kafka>=2.5.0` 依赖(从 `aiokafka>=0.10.0` 切换而来,用户明确偏好 confluent-kafka)
- [x] 10.3 创建 `backends/kafka_stream.py`,实现 `KafkaStreamBackend(StreamBackend)` 类,定义 6 个抽象方法的 Kafka 实现
- [x] 10.4 字段编解码:value / key / headers 三个编解码 helper(`_encode_value` / `_decode_value` / `_encode_headers` / `_decode_headers`),支持 bytes / str / dict / list 四种业务载荷类型
- [x] 10.5 `publish`:`AIOProducer.produce(topic, value, key, headers)` 返回 `asyncio.Future`,await 后拿到 `delivered Message`,返回 `f"{partition}:{offset}"` 作为业务 ID;`KafkaException` / `BufferError` 包装为 `MessageStreamError`
- [x] 10.6 `consume`:`AIOConsumer.poll(timeout_sec)` 循环取一批消息,`_PARTITION_EOF` 错误不视为异常(单条 poll 时常遇到),普通错误包装为 `MessageStreamError`
- [x] 10.7 `ack`:`TopicPartition(topic, partition, offset+1)` commit 下一条要消费位置,`asynchronous=False` 同步等待 broker 确认;`Message.offset` 是 `<partition>:<offset>` 字符串
- [x] 10.8 `create_group`:Kafka consumer group 是 lazy 自动 join,这里只 `AdminClient.create_topics` 确保 topic 存在,`TOPIC_ALREADY_EXISTS` 幂等
- [x] 10.9 `claim_idle`:退化为「seek to committed 重读未 commit 区间」,`asyncio.to_thread` 包装 `consumer.assignment` / `committed` / `seek` 三个同步调用
- [x] 10.10 `shutdown`:依次 `await consumer.close()` 清空 `_consumers` → `await producer.close()` → admin 句柄 = None;各步异常 try/except 容忍(警告日志)
- [x] 10.11 懒加载 + 并发保护:`AIOProducer` / `AdminClient` / `AIOConsumer` 均 async lock 首次创建,按 `(topic, group_id, consumer_id)` 缓存 consumer
- [x] 10.12 客户端配置中心化:提取 `_base_config()` 统一管理 `bootstrap.servers` / `security.protocol` / SASL 参数,producer/consumer/admin 各自加专属字段
- [x] 10.13 单元测试:8 个 Kafka 字段编解码测试 + 2 个 shutdown 顺序测试 + 4 个 init_from_settings / create_backend / is_kafka 属性测试,全部 Mock 不需真 Kafka
- [x] 10.14 集成测试:1 个 claim_idle seek 行为测试 + 1 个完整 init_from_settings 启用验证
- [x] 10.15 验证:66/66 单元 / 集成测试全绿,运行时间 0.70s


