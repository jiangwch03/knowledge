## Context

### 现状
- Redis Stream 的协议操作(XADD/XREADGROUP/XACK/XAUTOCLAIM)与日志业务深度耦合在 `knowledge-common/src/knowledge_common/service/log_service.py` 一个文件里
- 协议层与业务层无边界,业务层直接调 XADD/XREADGROUP
- 当前唯一 Stream 消费者是日志聚合,即将新增 RAG 端"文档解析+拆分"长流程任务(分钟级、5 步、强可观测性需求)
- 项目里已有现成的 `RedisPubSubUtil`(utils 层)范式,以及 `auto_register_routers` 业务方声明路径扫描范式

### 约束
- 跟 `RedisPubSubUtil` 风格对仗(但位置在 service/ 而非 utils/)
- 跟 `auto_register_routers` 业务方声明路径范式一致
- Python 异步生态(FastAPI 风格)
- 业务层零感知 ack / 拉取 / 分发
- 业务方传递消费者所在包路径,框架按需扫描

### 利益相关方
- `knowledge-admin` 项目:日志聚合场景
- `knowledge-rag` 项目:未来文档解析/拆分长流程任务
- `knowledge-common` 维护者:新模块的归宿
- 未来切 Kafka 时:所有调用方零修改

## Goals / Non-Goals

### Goals
1. 提供 Kafka 风格 API:`@consumer(topic, group_id, ...)` 装饰器 + `produce(topic, value, key=...)` 方法
2. 消息结构 `Message` 字段对齐 Kafka,切 Kafka 时字段零调整
3. 推送带重试(默认 3 次,业务可定制 `max_retries` / `retry_interval`),失败抛 `MessageStreamError`
4. 业务层不感知 ack / 消息拉取 / 分发 / 重试接管(由后端协议兜底)
5. 业务方在 lifespan 里 `register_consumer_paths([...])` 声明消费者位置,框架按需 import 扫描(对齐 `auto_register_routers` 范式)
6. 抽象后端 `StreamBackend` 屏蔽 Redis Stream 与 Kafka 的协议差异,切后端 2~3 天内完成,业务侧零修改
7. 命名中性(`MessageStreamService`)、位置合理(service/)、参数名 Kafka 风格,确保切 Kafka 时装饰器、门面、消息结构、注册 API 全部零修改

### Non-Goals
- **不做通用可靠消息总线框架**:不抽象 Saga / Outbox / 幂等装饰器 / 消息轨迹,这些是业务编排层职责
- **不做业务状态表设计**:业务对象状态由各业务系统(关系库)自己管,本服务不持有业务状态
- **不做业务事务协调**:状态推进、补偿等留给业务层
- **不做同步版 produce 完整实现**:仅留 `produce_sync` 接口占位,异步为主
- **不做 Kafka 后端实现**:阶段 1 不实现,阶段 2(切 Kafka 时)再写 `backends/kafka.py`
- **不改造现有日志模块**:本 change 只提供新服务能力,日志模块改造为下一 change
- **不实现文档处理业务**:独立 change
- **不做服务发现 / 多实例协调**:消费组机制由后端协议提供,框架不重复造
  - **举例**:3 个 admin 进程以同 `group_id="log_writer"` 订阅 `log:op`,A / B / C 各自调 `xreadgroup` 分别拿到 1~10、11~20、21~30 号消息,互不重复,框架完全不参与分配
  - **边界**(框架不做什么 / 后端协议做什么):
    - 框架**不维护**“实例注册表”、**不发送心跳**、**不触发重平衡**,也不暴露“我现在是第几个实例”、“全局还有几个 consumer 在跑”之类的 API
    - Redis Stream:由 `xreadgroup` 的 `LAST_DELIVERED_ID` 机制保证“同 group 内不重复”
    - Kafka:由 broker 的 GroupCoordinator 协议负责分区分配 / 心跳 / 重平衡
  - **边界失效情形**(何时需要重新评估这个决定):
    - **消费速度严重不均**(慢节点拖垮全组):后端协议只保证“不重复”,不保证“均匀”,由业务方调 `count` / 增 partition 数,框架不强行干预
    - **进程频繁挂掉、PEL 堆积**(Stream 专属):`min_idle_ms` 后 `xautoclaim` 让其他 worker 接管,框架靠装饰器后台协程兜底
    - **业务要“按业务键精准路由”**(超越后端协议能力):例 RAG 文档处理要求“同一 `doc_id` 的所有消息必须被同一个 worker 处理”以保证单文档串行;后端 partition key(Kafka 强 / Stream 弱)只能做“按 hash 路由”,不能做“按状态路由”,此时业务层自行过滤或改造一致性 hash,框架不替业务做
    - **跨语言消费**(例 C++ 服务也要消费同一 group):后端协议中性,其他语言用原生客户端,业务契约靠 Message 结构对齐(本 change 已对齐 Kafka 字段)

## Decisions

- 门面命名 `MessageStreamService`:中间件无关,切 Kafka 命名不变
- 放 `message_stream/` 子包:有生命周期和注册机制,不属于 utils,也不混入业务 service
- 方法名 `produce`:对齐 confluent-kafka
- 装饰器参数 `topic` + `group_id`:对齐 Kafka 客户端原生参数
- 装饰器独立文件 `consumer.py`:与门面分开
- Message 字段 `topic / key / value / headers / timestamp / offset / partition`:对齐 Kafka;留 `stream / payload` 别名兼容
- 业务方 `register_consumer_paths()` 传路径:对齐 `auto_register_routers` 范式
- 业务层不感知 ack / 拉取 / 分发 / 重试:基础设施由框架 + 后端协议接管
- `produce` 重试默认 3 次,失败抛 `MessageStreamError`:业务自己 try/except
- 抽象后端 6 个方法:`publish / consume / ack / create_group / claim_idle / shutdown`
- Kafka 客户端选 confluent-kafka-python 2.14+(`confluent_kafka.aio.AIOProducer` / `AIOConsumer` ,librdkafka 同步 API + 内部 ThreadPoolExecutor 包装)
- 4 个埋点:业务 ID 自管 / 幂等键业务声明 / 顺序用 key 参数 / 异常语义统一
- **配置驱动后端选择**:`MessageStreamSettings.message_stream_backend` 控制后端类型,业务方在 lifespan 中调 `MessageStreamService.init_from_settings(settings, redis=app.state.redis)`,内部走 `create_backend` 工厂;切换只改 .env 一行,业务零修改
- **后端工厂模式**:`create_backend(settings, redis)` 集中收口后端选择,未知后端类型抛 `MessageStreamError`;Redis 后端需要显式传入 redis 客户端,Kafka 后端可选
- **5 个 .env 文件统一补齐 20 个 `MESSAGE_STREAM_*` 字段**:后端选择 + 消费参数 + Redis MAXLEN + Kafka 全量参数(bootstrap / SASL / SSL / acks / linger / session / heartbeat / auto.offset.reset / topic partitions / replication factor)
- **KafkaStreamBackend 资产**:`admin/rag server.py` lifespan 统一改用 `init_from_settings` 范式(替换原硬编码 `MessageStreamService.init(RedisStreamBackend(...))`)

## Risks / Trade-offs

### 风险 1:装饰器 + import 副作用
- **风险**:框架在 lifespan 中主动 import 业务模块触发装饰器注册,如果业务模块 import 链复杂(import 时副作用大),可能影响启动速度或引发循环依赖
- **缓解**:
  - 业务模块 import 应当是轻量级(只定义函数,不执行重操作)
  - 框架提供 `discover_only`(只扫描不启动),便于测试
  - 文档明确要求"@consumer 装饰的模块不应该在 import 时执行耗时操作"

### 风险 2:业务方忘记调 `register_consumer_paths`
- **风险**:业务方漏调,消费者未注册,消息没人消费
- **缓解**:
  - 框架在 `discover_and_start` 时检查 `cls._scan_paths` 为空,打印警告日志
  - 框架在 `discover_and_start` 时检查注册到的消费者数量,如果某个常见 topic(如 `log:operation`)没有消费者,打印告警
  - 文档明确给出 lifespan 注入范式(三个步骤:init / register_consumer_paths / discover_and_start)

### 风险 3:路径冲突 / 重复注册
- **风险**:多个子应用(同进程)调用 `register_consumer_paths`,路径列表累加
- **缓解**:
  - 框架提供 `reset()` 方法清空状态,测试场景用
  - 装饰器去重:同一函数(模块路径 + 函数名)只注册一次
  - `discover_and_start` 前对路径列表去重

### 风险 4:切 Kafka 时部分功能差异需要适配 ~~【已缓解】~~
- **风险**:Kafka 没有"卡住消息接管"概念(Stream 的 XAUTOCLAIM)
- ~~**缓解**~~ **落地状态**(本 change 已交付):
  - `claim_idle` 在 `KafkaStreamBackend` 中退化为「seek to committed + 重读未 commit 区间」:调 `consumer.assignment()` 取已分配 partitions → `consumer.committed()` 查已提交 offset → 对 `offset >= 0` 的分区 `consumer.seek(tp)` 重读;Stream 侧的 `xautoclaim` 由 RedisStreamBackend 原生实现
  - 业务层无感知,只是后端实现差异
  - `create_group` 同样有差异:Stream 用 `xgroup create MKSTREAM`(幂等 BUSYGROUP),Kafka 是 lazy 自动 join + `AdminClient.create_topics` 确保 topic 存在(幂等 TOPIC_ALREADY_EXISTS);业务侧仍调同一个 `create_group` 抽象方法
  - 已交付:backends/kafka_stream.py + 4 个相关单测 + 1 个真实集成测试(6 个抽象方法均覆盖)

### 风险 5:同步 API 暂未实现,可能临时需要
- **风险**:某些场景(CLI 工具、启动脚本)需要同步发送
- **缓解**:
  - 留 `produce_sync` 接口签名,实际未实现时抛 `NotImplementedError` 提示
  - 业务需要时单独 change 补实现

### 风险 6:confluent-kafka 异步包装的事件循环问题 ~~【已缓解】~~
- **风险**:FastAPI 异步生态 + confluent-kafka `aio` 模块在不同事件循环下可能有踩坑
- ~~**缓解**~~ **落地状态**(本 change 已交付):
  - `AIOProducer` / `AIOConsumer` 在 `__init__` 时启动内部 ThreadPoolExecutor(`max_workers` 参数控制并发度),所有阻塞调用被 C 绑定 `produce()` / `poll()` / `commit()` 封装为 awaitable
  - `AdminClient` 是同步 API,被 `asyncio.to_thread` 包装(`create_topics` / `consumer.assignment` / `consumer.committed` / `consumer.seek`),事件循环不阻塞
  - 实际安装版本:confluent-kafka 2.14.2(在 macOS 上需先 `brew install librdkafka`)
  - 验证:`KafkaStreamBackend` 4 个 Kafka 专项单测 + 1 个 claim_idle seek 集成测试全绿,未发现事件循环问题
  - 业务侧零修改

## Migration Plan

### 阶段 1:Redis Stream 后端(本 change,8~10 天)

**T1.1 模块骨架搭建(1 天)**
- 创建 `knowledge_common/message_stream/` 子包
- `__init__.py` 统一导出
- `exceptions.py` 定义 `MessageStreamError`
- `message.py` 定义 `Message` 数据类

**T1.2 抽象后端(1 天)**
- `backends/base.py` 定义 `StreamBackend` 抽象接口(6 个方法)
- 编写接口文档与单元测试 stub

**T1.3 RedisStreamBackend 实现(1 天)**
- `backends/redis_stream.py` 基于 redis.asyncio 实现
- 适配 Message 字段(Stream id → offset,fields 拆 headers + value)
- 处理 BUSYGROUP 幂等、BUSYGROUP 异常、消息 ID 格式

**T1.4 @consumer 装饰器 + 路径注册(2 天)**
- `consumer.py` 装饰器定义
- `service.py` 实现 `register_consumer_paths` / `discover_and_start` / `shutdown`
- 全路径 import + 反射 + 后台协程拉起
- 重复注册保护、路径去重、reset 方法

**T1.5 门面 MessageStreamService(2 天)**
- `produce` 方法(带重试、参数校验、异常包装)
- 装饰器触发的消费者后台协程(双层循环、异常自愈)
- 任务名管理、shutdown 钩子
- 跟 RedisPubSubUtil 风格对仗的日志格式

**T1.6 单元测试(1~2 天)**
- Message 数据类单元测试
- RedisStreamBackend 单元测试(fakeredis / 真 redis)
- 装饰器注册流程测试
- produce 重试测试

**T1.7 文档(半天)**
- README + 装饰器使用示例
- 切 Kafka 的"埋点"清单
- 跟 Pub/Sub 工具类的对仗说明

### 阶段 2:日志模块迁移(独立 change,2~3 天)

- 不在本 change 范围
- 改造 `log_service.py` 用 `MessageStreamService` + `@consumer` 装饰器
- 跑通日志聚合,验证零行为变化
- 旧代码可保留作为 fallback,逐步切换

### 阶段 3:切 Kafka(~~独立 change,2~3 天,几个月后~~) **本 change 已落地**

- ✅ 实现 `backends/kafka_stream.py` 用 `confluent_kafka.aio.AIOProducer` / `AIOConsumer`(同 change 阶段 1 同步交付)
- ✅ `.env` 配置改 `MESSAGE_STREAM_BACKEND=kafka`,lifespan 注入零修改(`init_from_settings` 自动按 .env 选后端)
- ✅ 业务层零修改验证:装饰器、produce、Message 全部不变
- ⏳ 集成测试(testcontainers 起真 Kafka)暂未交付,后续 change 可补
- 阶段 3 与阶段 1 合并交付的原因:`StreamBackend` 抽象边界清晰 + confluent-kafka 异步 API 与 FastAPI 生态兼容,不需要独立验证 2~3 天
- 现状态:**5 个 .env 文件已含 20 个 `MESSAGE_STREAM_*` 字段**;`admin/rag server.py` 已改为 `init_from_settings` 范式;66/66 单测全绿

### 回滚策略

- 阶段 1:删除 `message_stream/` 子包即可,无破坏性(旧 `log_service.py` 独立运行)
- 阶段 2:旧 `log_service.py` 保留,新旧并行,新代码有问题切回旧代码
- 阶段 3:旧后端实现保留,新后端有问题改 .env 即可切换

## Open Questions

1. **`produce_sync` 是否需要首版实现?**
   - 倾向:留接口占位,首版不实现
   - 待定:业务方如有同步场景(CLI / 启动脚本)需补实现

2. **批量消费装饰器语法?**
   - 候选:`@consumer(topic, group_id, batch_size=100)`
   - 候选:`@batch_consumer(topic, group_id)` 独立装饰器
   - 倾向:首版只做单条消费,批量后续按需

3. **模式订阅装饰器语法?**
   - 候选:`@consumer(topic_pattern="log:*", group_id="...")`
   - 倾向:首版只做精确 topic,模式订阅后续按需

4. **测试策略?**
   - 倾向:A,平衡速度与真实性
   - **落地状态**:`test_message_stream.py` 采用 3 层验证:
     - Mock 层:AsyncMock 模拟 StreamBackend 6 个方法,跑 `Message` / `MessageStreamError` / `@consumer` / `produce` 重试 / `discover_and_start` 扫描(运行稳定,不依赖外部中间件)
     - Kafka 专项层:针对 `KafkaStreamBackend` 的字段编解码、shutdown 顺序、init_from_settings 调用、`is_kafka` / `is_redis` 属性(纯 Python 对象,不需真 Kafka)
     - Redis 端到端层:6379 端口未连通时自动 skip,连通时跑真实 produce→consume→ack 全链路 + `init_from_settings` + `create_backend` 全部能力

5. **多消费者在同进程/同 topic 的并发?**
   - 当前设计:同一 group_id 下多消费者由后端协议协调(Stream 抢 / Kafka 分 partition)
   - 待验证:多 group_id 订阅同 topic 是否需要并发控制
   - 倾向:框架不重复造轮子,信任后端协议

6. **`discover_and_start` 失败时是否回滚已启动的消费者?**
   - 当前设计:启动失败的消费者单独记录,不影响其他
   - 待验证:批量启动时部分失败的处理

7. **业务方忘了 register_consumer_paths,框架的兜底机制具体形式?**
   - 当前设计:警告日志 + 启动 0 个消费者
   - 候选增强:在生产模式下启动失败抛异常(强制业务方正确配置)
   - 倾向:开发模式警告,生产模式抛异常(由 `env` 控制)
