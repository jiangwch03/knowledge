## 1. 框架包骨架搭建

- [x] 1.1 创建 `knowledge-common/src/knowledge_common/broadcast/` 包目录结构：`__init__.py`、`subscriber.py`、`service.py`、`message.py`、`exceptions.py`、`backends/__init__.py`、`backends/base.py`、`backends/redis_pubsub.py`
- [x] 1.2 实现 `exceptions.py`：定义 `BroadcastError` 异常类（含 channel、cause 字段）
- [x] 1.3 实现 `message.py`：定义 `BroadcastMessage` 数据类（channel、payload、timestamp 字段）

## 2. 抽象层与后端实现

- [x] 2.1 实现 `backends/base.py`：定义 `BroadcastBackend` 抽象基类（subscribe、publish、unsubscribe、shutdown 四个抽象方法）
- [x] 2.2 实现 `backends/redis_pubsub.py`：`RedisPubSubBackend` 单连接多路分发实现，包含共享 pubsub 对象、dispatch table、listen loop（自动重连 + handler 异常隔离）、动态增减 channel 订阅

## 3. 装饰器与门面服务

- [x] 3.1 实现 `subscriber.py`：`@subscriber(channel, id=None)` 装饰器工厂 + `SubscriberInfo` 数据类，注册到 `BroadcastService._subscribers`
- [x] 3.2 实现 `service.py`：`BroadcastService` 门面（全 @classmethod），包含 `init(redis)`、`register_subscriber_paths(paths)`、`discover_and_start()`、`publish(channel, payload)`、`shutdown()`、`reset()`
- [x] 3.3 实现 `__init__.py`：导出 `BroadcastService`、`subscriber`、`BroadcastMessage`、`BroadcastError`

## 4. 业务层订阅者目录创建

- [x] 4.1 创建 `knowledge-common/src/knowledge_common/message/subscriber/__init__.py`
- [x] 4.2 创建 `knowledge-admin/src/knowledge_admin/message/subscriber/__init__.py`
- [x] 4.3 创建 `knowledge-content/src/knowledge_content/message/subscriber/__init__.py`

## 5. 定时任务广播消费者迁移

- [x] 5.1 创建 `knowledge-common/src/knowledge_common/message/subscriber/scheduler_subscriber.py`：将 `SchedulerUtil._on_global_sync_message` 逻辑拆出为 `@subscriber(channel='scheduler:global:sync')` 装饰的独立函数
- [x] 5.2 修改 `SchedulerUtil.broadcast_scheduler_sync()`：内部改调 `BroadcastService.publish()` 替代 `RedisPubSubUtil.publish()`
- [x] 5.3 修改 `SchedulerUtil.broadcast_execute_job_once()`：同上改调 `BroadcastService.publish()`
- [x] 5.4 移除 `SchedulerUtil._start_scheduler_as_leader()` 中手动调用 `RedisPubSubUtil.subscribe()` 的代码

## 6. lifespan 接入

- [x] 6.1 修改 `knowledge-admin/src/knowledge_admin/server/server.py`：新增 `_init_broadcast(app)` 方法（init → register_subscriber_paths → discover_and_start），在 lifespan 中 Redis 初始化之后调用
- [x] 6.2 修改 `knowledge-content/src/knowledge_content/server/server.py`：同上新增 `_init_broadcast(app)` 并接入 lifespan
- [x] 6.3 在两个项目的 lifespan shutdown 阶段加入 `await BroadcastService.shutdown()`

## 7. 验证与测试

- [x] 7.1 编写单元测试：验证 `@subscriber` 装饰器注册、去重、BroadcastMessage 解析
- [x] 7.2 编写单元测试：验证 `BroadcastService` 生命周期（init → discover → shutdown）
- [x] 7.3 编写集成测试：验证 publish → subscriber handler 收到消息的端到端链路
- [x] 7.4 启动 admin 项目，验证定时任务广播功能正常工作（新增/编辑/删除任务触发 rag 同步）
