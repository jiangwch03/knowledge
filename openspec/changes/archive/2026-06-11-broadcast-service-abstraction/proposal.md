## Why

当前定时任务变更的全局广播通知直接耦合 `RedisPubSubUtil`，业务代码需感知 Redis Pub/Sub 的连接管理、JSON 序列化、重连逻辑等底层细节。随着项目演进，缓存失效通知、配置热更新等场景也将使用广播机制，现有耦合方式无法满足多场景复用和后端可替换的需求。需要提供一个与 `MessageStreamService`（消息队列）对等的 `BroadcastService`（消息广播）抽象层，让业务代码通过 `@subscriber` 装饰器和 `publish()` 门面方法完成广播收发，完全隔离 Redis 操作。

## What Changes

- **新增 `broadcast` 框架包**（`knowledge-common/src/knowledge_common/broadcast/`）：提供 `BroadcastService` 门面、`@subscriber` 装饰器、`BroadcastMessage` DTO、`BroadcastBackend` 抽象基类及 `RedisPubSubBackend` 实现。
- **Backend 采用单连接多路分发**：一个共享 `redis.pubsub()` 对象 + 内部 dispatch table，所有 channel 复用同一 TCP 连接和后台 Task。
- **新增业务层订阅者目录**：`knowledge-common/message/subscriber/`（通用订阅者）、`knowledge-admin/message/subscriber/`、`knowledge-content/message/subscriber/`（各项目专属）。
- **迁移定时任务广播消费者**：将 `SchedulerUtil._on_global_sync_message` 拆出为独立 `@subscriber` 函数，放在 `knowledge-common/message/subscriber/scheduler_subscriber.py`。
- **迁移定时任务广播发布者**：`SchedulerUtil.broadcast_scheduler_sync()` 内部改调 `BroadcastService.publish()`，不再直接引用 `RedisPubSubUtil`。
- **lifespan 接入**：各项目 `server.py` 新增 `_init_broadcast()` 三步范式（init → register_subscriber_paths → discover_and_start），对齐 MessageStreamService 风格。

## Capabilities

### New Capabilities

- `broadcast-service`: BroadcastService 消息广播框架，包含 @subscriber 装饰器注册、启动扫描、publish 门面、BroadcastBackend 抽象及 RedisPubSubBackend 单连接多路分发实现。

### Modified Capabilities

- `job-app-scope-isolation`: 定时任务广播发布/订阅改为通过 BroadcastService 抽象层，不再直接耦合 RedisPubSubUtil。

## Impact

- **核心代码**：`knowledge-common` 新增 `broadcast/` 包（约 6 个文件）；`message/subscriber/` 新增 `scheduler_subscriber.py`。
- **改动代码**：`SchedulerUtil`（发布侧改调 BroadcastService，订阅侧移除手动 subscribe 逻辑）；admin/rag 的 `server.py`（新增 broadcast 初始化）。
- **依赖**：无新增外部依赖，复用现有 `redis.asyncio`。
- **兼容性**：`RedisPubSubUtil` 保留但降级为内部工具（Backend 可选复用其部分逻辑），对外接口统一收敛为 `BroadcastService`。
