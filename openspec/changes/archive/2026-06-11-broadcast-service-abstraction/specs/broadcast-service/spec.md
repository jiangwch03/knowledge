## ADDED Requirements

### Requirement: @subscriber 装饰器声明式注册

业务方 SHALL 通过 `@subscriber(channel='<channel_name>')` 装饰器声明广播消费者函数。装饰器 SHALL 立即将函数注册到 `BroadcastService._subscribers` 全局表，key 为 `{module}.{func.__name__}`。同一函数重复装饰 SHALL 跳过，不抛异常。

#### Scenario: 声明一个广播订阅者
- **WHEN** 业务模块中定义 `@subscriber(channel='scheduler:global:sync') async def on_sync(msg): ...`
- **THEN** 函数被注册到全局表，key 为模块全路径 + 函数名，绑定 channel 为 `scheduler:global:sync`

#### Scenario: 同一函数重复装饰
- **WHEN** 同一函数被 `@subscriber` 装饰两次（如热加载场景）
- **THEN** 框架 SHALL 跳过重复注册，仅保留首次，不抛异常

### Requirement: BroadcastService.publish 发布接口

`BroadcastService.publish(channel, payload)` SHALL 为异步类方法，将 payload（dict/str）通过后端发布到指定 channel。payload 为 dict 时 SHALL 自动 JSON 序列化。未 init 时调用 SHALL 抛 `BroadcastError`。

#### Scenario: 正常发布
- **WHEN** 业务代码调用 `await BroadcastService.publish('cache:invalidate', {'key': 'user:123'})`
- **THEN** 消息 SHALL 被序列化并通过后端发布到 `cache:invalidate` channel

#### Scenario: 未初始化时发布
- **WHEN** 业务代码在 `BroadcastService.init()` 未调用时调用 `publish()`
- **THEN** SHALL 抛出 `BroadcastError`，提示未初始化

### Requirement: BroadcastService 生命周期管理

`BroadcastService` SHALL 提供以下生命周期方法：
- `init(redis)`: 注入 Redis 客户端，创建后端实例
- `register_subscriber_paths(paths)`: 声明订阅者扫描路径，多次调用幂等累加
- `discover_and_start()`: 扫描路径触发装饰器注册，为所有已注册订阅者启动监听
- `shutdown()`: 取消监听、关闭后端连接、清理状态

#### Scenario: 标准三步接入
- **WHEN** lifespan 中依次调用 `init(redis)` → `register_subscriber_paths([...])` → `await discover_and_start()`
- **THEN** 所有声明路径下的 `@subscriber` 函数 SHALL 被扫描注册，后端监听 SHALL 启动

#### Scenario: 未注册路径时启动
- **WHEN** `discover_and_start()` 被调用但 `register_subscriber_paths` 未调用
- **THEN** SHALL 打印警告日志，启动 0 个订阅者（开发模式友好）

#### Scenario: 应用关闭
- **WHEN** lifespan 退出阶段调用 `await BroadcastService.shutdown()`
- **THEN** 后端监听 Task SHALL 被取消，pubsub 连接 SHALL 关闭

### Requirement: BroadcastMessage 统一消息结构

handler 接收的消息 SHALL 为 `BroadcastMessage` 数据类，包含字段：
- `channel: str` — 消息来源 channel
- `payload: dict | str` — 自动 JSON 反序列化后的载荷
- `timestamp: float` — 消息接收时间戳

#### Scenario: handler 接收标准消息
- **WHEN** channel 收到 JSON 格式消息
- **THEN** handler 接收的 `msg.payload` SHALL 为反序列化后的 dict，`msg.channel` 为频道名

#### Scenario: handler 接收非 JSON 消息
- **WHEN** channel 收到纯文本消息
- **THEN** handler 接收的 `msg.payload` SHALL 为原始字符串

### Requirement: BroadcastBackend 抽象基类

`BroadcastBackend` SHALL 定义以下抽象方法：
- `async subscribe(channels, dispatch_fn)`: 订阅多个 channel 并开始监听
- `async publish(channel, message)`: 发布序列化后的消息
- `async unsubscribe(channel)`: 取消单个 channel 订阅
- `async shutdown()`: 关闭所有连接和监听

#### Scenario: 后端可替换性
- **WHEN** 新增一个 BroadcastBackend 实现（如 NATS）
- **THEN** 只需实现上述 4 个方法，业务代码和 BroadcastService 门面零修改

### Requirement: RedisPubSubBackend 单连接多路分发

`RedisPubSubBackend` SHALL 使用单个 `redis.pubsub()` 对象订阅所有 channel，通过内部 dispatch table 将消息路由到对应 handler。SHALL 支持：
- 动态增量订阅/退订 channel
- 连接异常时自动重连并恢复所有 channel 订阅
- 单个 handler 异常不影响整体 listen loop

#### Scenario: 多 channel 共享连接
- **WHEN** 框架注册了 3 个不同 channel 的订阅者
- **THEN** Backend SHALL 仅创建 1 个 pubsub 连接和 1 个后台 Task，内部按 channel 分发

#### Scenario: 连接断开自动重连
- **WHEN** Redis 连接因网络异常断开
- **THEN** Backend SHALL 自动重连，重连成功后重新 subscribe 所有已注册 channel

#### Scenario: handler 异常隔离
- **WHEN** 某个 handler 抛出未捕获异常
- **THEN** 该异常 SHALL 被记录日志，不影响其他 handler 和 listen loop 继续运行

### Requirement: discover_and_start 自动扫描

`BroadcastService.discover_and_start()` SHALL 主动 import 业务方声明路径下的所有模块，触发 `@subscriber` 装饰器注册，再启动后端监听。扫描 SHALL 递归处理子包。

#### Scenario: 启动时扫描
- **WHEN** `discover_and_start()` 被调用
- **THEN** 框架 SHALL import 所有声明路径下的模块，装饰器把函数注册到全局表，后端 listen 被启动

#### Scenario: import 失败容错
- **WHEN** 扫描路径下某个模块 import 失败
- **THEN** SHALL 打印错误日志并跳过该模块，不阻塞其他模块的注册和启动
