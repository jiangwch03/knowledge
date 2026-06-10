# knowledge-common

`knowledge-common` 是项目的公共基础库,封装跨子项目复用的能力(数据访问、配置、上下文、消息流、调度、Pub/Sub、日志聚合、事务装饰器等),由 `knowledge-admin` / `knowledge-rag` 等子项目通过 uv workspace 引用。

> 设计原则:**通用归 common,业务归子项目**。所有"换中间件就要改的"基础设施都收敛到 common,业务层只对接 common 暴露的门面 / 装饰器。

## 目录速览

| 子模块 | 职责 |
|---|---|
| `common/` | 跨模块通用件:上下文(`ContextVar`)、注解(`@transactional`)、切面、路由自动注册 |
| `config/` | 配置加载、DB / Redis / Scheduler 客户端注入 |
| `dao/` | 通用 DAO 基类 |
| `entity/` | ORM 实体 |
| `message_stream/` | **消息流服务**(Kafka 风格门面,Redis Stream / Kafka 可插拔后端) |
| `middlewares/` | FastAPI 中间件(异常、日志、上下文注入等) |
| `service/` | 通用服务(日志聚合、配置 / 字典缓存等) |
| `sub_applications/` | 子应用 Mount |
| `utils/` | 工具类(Redis Pub/Sub、加密、IP、时间等) |

---

## 消息流服务(`message_stream/`)

Kafka 风格的 Python 消息流门面,业务层用 `@consumer` 装饰器声明消费点、用 `produce` 推送消息。底层 Redis Stream / Kafka 双后端可插拔,切后端时业务代码、装饰器签名、门面 API、消息结构**全部零修改**。

### 核心 API

```python
from knowledge_common.message_stream import (
    MessageStreamService,   # 门面(全 @classmethod)
    consumer,               # @consumer 装饰器
    Message,                # 消息结构(对齐 Kafka 字段)
    MessageStreamError,     # 统一异常
)
from knowledge_common.message_stream.backends.redis_stream import RedisStreamBackend
```

### 接入范式(lifespan 三步)

```python
# 1. 业务方在任意模块顶层声明消费者(装饰器自动注册到 _consumers)
@consumer(topic='log:op', group_id='log_writer')
async def handle_log_op(msg: Message) -> None:
    # 业务正常返回 → 框架自动 ack
    # 业务抛异常    → 框架不 ack,由后端协议兜底(Stream PEL 接管 / Kafka 重平衡)
    print(msg.value, msg.key)

# 2. FastAPI lifespan 启动阶段:init → register_consumer_paths → discover_and_start
async def _start_background_tasks(app):
    MessageStreamService.init(RedisStreamBackend(app.state.redis))
    MessageStreamService.register_consumer_paths([
        'knowledge_admin.service',   # 业务方声明扫描路径(可累加)
    ])
    await MessageStreamService.discover_and_start()

# 3. 关闭阶段:统一 shutdown(取消所有后台协程,释放后端连接)
async def _stop_background_tasks(app):
    await MessageStreamService.shutdown()
```

### 推送消息

```python
try:
    msg_id = await MessageStreamService.produce(
        topic='log:op',
        value={'op': 'login', 'user_id': 1},
        key='user_1',              # 业务键(顺序保证 / partition 路由用)
        headers={'trace_id': 'x'},
        max_retries=3,             # 默认 3 次重试
        retry_interval=0.5,        # 重试间隔(秒)
    )
except MessageStreamError as e:
    # 业务方自行决定:告警 / 落失败表 / 丢弃 / 重投
    logger.error(f'push 失败: {e}')
```

### Message 字段(对齐 Kafka)

| 字段 | 类型 | 说明 |
|---|---|---|
| `topic` | `str` | 主题 |
| `key` | `str \| None` | 业务键(Kafka partition key / Stream 业务过滤键) |
| `value` | `Any` | 载荷(自动 JSON 序列化) |
| `headers` | `dict` | 头部元数据 |
| `timestamp` | `int` | 毫秒时间戳 |
| `offset` | `str` | 消息位置(Stream `xid` / Kafka offset) |
| `partition` | `int \| None` | 分区号(Stream 无分区,值为 `None`) |
| `stream` *(别名)* | `str` | ≡ `topic`,平滑过渡老代码 |
| `payload` *(别名)* | `Any` | ≡ `value`,平滑过渡老代码 |

### 与 `RedisPubSubUtil` 的对仗

| 维度 | `RedisPubSubUtil` | `MessageStreamService` |
|---|---|---|
| 位置 | `utils/`(无状态工具) | `service/`(有生命周期 + 注册机制) |
| 中间件 | Redis Pub/Sub(扇出广播) | Redis Stream / Kafka(可靠队列) |
| 消息可靠性 | 离线订阅者收不到(可丢) | 消费组 + ack / PEL(不丢) |
| 业务接入 | 命令式 `subscribe()` + 回调 | 声明式 `@consumer` 装饰器 |
| 切 Kafka | 不支持(Pub/Sub 无对应) | **零修改**(契约对齐 Kafka) |
| 典型场景 | 调度同步、实时广播 | 日志聚合、文档解析编排、长流程任务 |

> 详细的"切 Kafka 4 个埋点"约定见:[`docs/rag/message-stream-service-design.md`](../docs/rag/message-stream-service-design.md)。

### 设计要点

- **门面命名中性**:`MessageStreamService` 不以 `Redis` / `Kafka` 开头,切后端命名不变
- **装饰器参数 Kafka 化**:`topic` + `group_id` 与 confluent-kafka 原生参数一致
- **业务方路径声明**:对齐 `auto_register_routers` 范式,框架不硬编码项目结构
- **业务零感知 ack / 拉取 / 分发**:框架双层 `while True` 自愈,后端协议(PEL / 重平衡)兜底
- **统一异常 `MessageStreamError`**:业务 `try/except` 一次,无需分别处理 Stream / Kafka 协议异常
- **`reset()` + `shutdown()`**:测试可重复跑,生产优雅退出
- **lifespan 单点接入**:与 `auto_register_routers` / `SchedulerUtil` 等基础设施注入风格一致

---

## 运行测试

```bash
# 全部测试(项目根目录)
.venv/bin/pytest knowledge-common/tests -v

# 消息流服务专项
.venv/bin/pytest knowledge-common/tests/test_message_stream.py -v
```

测试套件分层:
- ✅ 静态 / Mock 层:任意环境可跑(46 项)
- ⚠️ 真 Redis 集成层:6379 未连通时自动 skip(1 项)
