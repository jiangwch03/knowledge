## Context

项目已有 `MessageStreamService` 提供消息队列能力（Redis Stream / Kafka 双后端），通过 `@consumer` 装饰器 + 启动扫描实现业务零感知注册。但广播通知（Redis Pub/Sub）场景仍直接耦合 `RedisPubSubUtil`，业务代码需手动管理订阅生命周期、了解 Redis 连接细节。

当前定时任务全局广播（`scheduler:global:sync`）是唯一的 Pub/Sub 使用者，handler 硬编码在 `SchedulerUtil` 内部，发布侧直接调用 `RedisPubSubUtil.publish()`。未来缓存失效、配置热更新等场景也需广播机制，需提供统一抽象。

## Goals / Non-Goals

**Goals:**

- 提供 `BroadcastService` 门面，对标 `MessageStreamService` 的三步接入范式
- 业务代码通过 `@subscriber` 装饰器声明消费者，通过 `BroadcastService.publish()` 发布消息，完全隔离 Redis 操作
- Backend 层采用单 pubsub 连接 + dispatch table 实现多 channel 复用，资源开销最小化
- 将定时任务广播消费者迁移为 `@subscriber` 模式，验证框架可用性

**Non-Goals:**

- 不替换 `MessageStreamService`（队列 vs 广播语义不同，独立共存）
- 不实现 Kafka / NATS / RabbitMQ 等非 Redis 广播后端（预留接口，按需扩展）
- 不改变定时任务广播的业务逻辑（app_scope 路由、leader 判断等保持不变）
- 不删除 `RedisPubSubUtil`（降级为内部工具，Backend 可选复用）

## Decisions

### Decision 1: 独立 `broadcast` 包，与 `message_stream` 平级

**选择**：新建 `knowledge_common/broadcast/` 顶层包。

**理由**：
- 广播（fire-and-forget、无持久化、一对多）与队列（持久化、消费组、ACK）语义完全不同
- 生命周期差异：Pub/Sub 可能绑定 leader 选举，Stream 始终运行
- 独立包便于理解、测试和未来独立演进
- `utils/` 是无状态工具集，不适合有状态的服务模块

### Decision 2: 单 pubsub 连接 + dispatch table

**选择**：Backend 内部仅创建一个 `redis.pubsub()` 对象和一个 listen Task，通过 `_dispatch: dict[str, list[handler]]` 多路分发。

**理由**：
- 避免 N channel = N 个 pubsub 对象 / N 个 TCP 连接的资源浪费
- Redis 协议原生支持单连接订阅多 channel
- 动态增减 channel 通过 `await pubsub.subscribe/unsubscribe` 增量操作
- 单 listen loop 简化异常处理和重连逻辑

### Decision 3: @subscriber 装饰器 + register_subscriber_paths 扫描

**选择**：对齐 `@consumer` 的注册范式。

**理由**：
- 开发者学会一个模式即可通用，零学习成本
- 框架主动 import 触发装饰器注册，业务模块保持声明式
- 支持多项目各自声明扫描路径，common 通用订阅者 + 项目专属订阅者并存

### Decision 4: BroadcastMessage DTO 隔离 Redis 细节

**选择**：handler 接收 `BroadcastMessage(channel, payload, timestamp)` 而非 Redis 原始消息。

**理由**：
- 业务代码不依赖 `PubSubMessage`（Redis 实现细节）
- 未来替换后端时 handler 签名不变
- payload 为 `dict | str`（自动 JSON 反序列化），对齐 MessageStreamService 的 Message.value 风格

### Decision 5: SchedulerUtil 保留业务封装方法

**选择**：`broadcast_scheduler_sync()` 保留为 SchedulerUtil 的业务方法，内部改调 `BroadcastService.publish()`。

**理由**：
- 该方法附加了 `worker_id`、`action` 等业务字段，属于业务逻辑而非框架职责
- `JobService` 调用方无需改动（接口不变，内部实现解耦）
- leader 判断逻辑保留在 handler 内部（`if not cls._is_leader: return`），简单有效

## Risks / Trade-offs

### Risk 1: 单 pubsub 连接断开影响所有 channel

- **风险**：共享连接断开时所有 channel 的消费暂停
- **缓解**：外层 while True 自动重连 + 重连后重新 subscribe 所有 channel；配合 10 秒轮询兜底策略，短暂断连不影响业务最终一致性

### Risk 2: handler 阻塞影响其他 channel 的消息派发

- **风险**：某个 handler 执行耗时过长会阻塞同一 listen loop 中其他消息的派发
- **缓解**：handler 中应只做轻量派发（如设置 flag、入队），重操作用 `asyncio.create_task` 异步执行；框架层对单次 handler 执行添加超时告警日志

### Risk 3: 启动顺序依赖

- **风险**：`BroadcastService.discover_and_start()` 必须在 Redis 连接建立之后
- **缓解**：对齐现有 lifespan 顺序（redis init → broadcast init），框架在 init 未调用时抛 `BroadcastError`
