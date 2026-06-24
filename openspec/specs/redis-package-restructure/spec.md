## ADDED Requirements

### Requirement: Redis 统一包结构
系统 SHALL 在 `knowledge_common/redis/` 下提供统一的 Redis 能力包，包含以下文件：
- `key.py` — `RedisKey` + `LockKey` 键名定义
- `connection.py` — `RedisConnection` 连接池管理（仅连接生命周期，不含业务缓存初始化）
- `client.py` — `RedisClient` CRUD 封装
- `pubsub.py` — `RedisPubSub` Pub/Sub 工具
- `lock.py` — `DistributedLock` 分布式锁
- `serialization.py` — 公共 JSON 序列化/反序列化
- `__init__.py` — 统一 re-export 入口

`RedisContext` 保留在 `common/context.py`，`RedisContextMiddleware` 保留在 `middlewares/redis_context_middleware.py`，均不纳入 `redis/` 包（它们是项目级上下文管理机制，非 Redis 能力）。

#### Scenario: 通过新路径访问 Redis 客户端
- **WHEN** 代码使用 `from knowledge_common.redis import RedisClient`
- **THEN** 系统 SHALL 正常导入且返回 CRUD 封装类

#### Scenario: 通过新路径访问 Key 定义
- **WHEN** 代码使用 `from knowledge_common.redis import RedisKey, LockKey`
- **THEN** 系统 SHALL 正常导入且返回键名定义类

#### Scenario: 通过新路径访问连接管理器
- **WHEN** 代码使用 `from knowledge_common.redis import RedisConnection`
- **THEN** 系统 SHALL 正常导入且返回连接池管理类（原 `RedisUtil`，已重命名）

### Requirement: RedisConnection 职责单一
`RedisConnection`（原 `RedisUtil`）SHALL 仅管理连接池生命周期（`create_redis_pool`、`close_redis_pool`、`check_redis_connection`、`get_redis`）。`init_sys_dict`/`init_sys_config` 缓存预热逻辑 SHALL 移出，回归 `DictDataService`/`ConfigService` Service 层。

#### Scenario: RedisConnection 不含缓存初始化方法
- **WHEN** 检查 `RedisConnection` 类的方法列表
- **THEN** SHALL 不包含 `init_sys_dict` 和 `init_sys_config` 方法

#### Scenario: 缓存预热由 Service 层提供
- **WHEN** 应用启动时需预热字典表缓存
- **THEN** SHALL 通过 `DictDataService` 的缓存初始化方法完成，而非通过 `RedisConnection`

#### Scenario: 缓存预热由 ConfigService 提供
- **WHEN** 应用启动时需预热参数配置缓存
- **THEN** SHALL 通过 `ConfigService` 的缓存初始化方法完成，而非通过 `RedisConnection`

### Requirement: 类名统一
以下类名 SHALL 统一清理：
- `RedisUtil` → `RedisConnection`
- `RedisPubSubUtil` → `RedisPubSub`
- `RedisClient`、`DistributedLock`、`RedisKey`、`LockKey` 保持不变
- `RedisContextMiddleware` 保持不变，保留在 `middlewares/`（不纳入 `redis/` 包）

#### Scenario: RedisConnection 类名已统一
- **WHEN** 代码使用 `from knowledge_common.redis import RedisConnection`
- **THEN** 系统 SHALL 正常导入（旧名 `RedisUtil` 不再存在）

#### Scenario: RedisPubSub 类名已统一
- **WHEN** 代码使用 `from knowledge_common.redis import RedisPubSub`
- **THEN** 系统 SHALL 正常导入（旧名 `RedisPubSubUtil` 不再存在）

### Requirement: 公共序列化模块
系统 SHALL 在 `knowledge_common/redis/serialization.py` 提供公共序列化函数：
- `serialize(value: Any) -> str` — Pydantic Model / dict / list / 基础类型 → JSON 字符串
- `deserialize(raw: str | None, model: type | None = None) -> Any` — JSON 字符串 → dict / Model 实例
- `encode_payload(payload: Any) -> str | bytes` — Pub/Sub 发布载荷编码
- `decode_message_data(data: str | bytes | None) -> Any` — Pub/Sub 消息数据解码

`RedisClient` 和 `RedisPubSub` SHALL 使用此公共模块替代各自的内部序列化实现。

#### Scenario: RedisClient 使用公共序列化
- **WHEN** `RedisClient.set()` 序列化一个 dict 值
- **THEN** 系统 SHALL 调用 `serialization.serialize()` 产生 JSON 字符串并存储

#### Scenario: RedisPubSub 使用公共序列化
- **WHEN** `RedisPubSub.publish()` 编码一个 dict payload
- **THEN** 系统 SHALL 调用 `serialization.encode_payload()` 产生 JSON 字符串并发布

### Requirement: 全量导入路径改造
迁移完成后，全项目所有旧路径引用 SHALL 统一替换为新包路径，旧文件 SHALL 删除：
- `knowledge_common.utils.redis_client` → `knowledge_common.redis.client`
- `knowledge_common.utils.redis_pubsub_util` → `knowledge_common.redis.pubsub`
- `knowledge_common.utils.distributed_lock` → `knowledge_common.redis.lock`
- `knowledge_common.common.redis_key` → `knowledge_common.redis.key`
- `knowledge_common.config.get_redis` → `knowledge_common.redis.connection`

`middlewares/redis_context_middleware.py` 路径不变（不纳入 `redis/` 包）。

#### Scenario: 全项目无旧路径残留
- **WHEN** 执行 grep 扫描全项目 `.py` 文件中的旧路径
- **THEN** SHALL 返回零匹配结果

#### Scenario: 跨子项目导入路径已改造
- **WHEN** `knowledge-admin` 和 `knowledge-content` 引用 Redis 相关类
- **THEN** SHALL 统一使用 `knowledge_common.redis.*` 新路径 + 新类名（`RedisConnection`、`RedisPubSub`）

### Requirement: 废弃 RedisInitKeyConfig 枚举清理
`RedisInitKeyConfig`（`common/enums.py`）已标注废弃但仍有 25+ 处活跃使用。本次重构 SHALL 将所有 `RedisInitKeyConfig.XXX.key` 替换为 `RedisKey.XXX` 常量，然后删除该枚举类。

替换映射：
- `RedisInitKeyConfig.ACCESS_TOKEN.key` → `RedisKey.ACCESS_TOKEN`
- `RedisInitKeyConfig.SYS_DICT.key` → `RedisKey.SYS_DICT`
- `RedisInitKeyConfig.SYS_CONFIG.key` → `RedisKey.SYS_CONFIG`
- `RedisInitKeyConfig.API_CACHE.key` → `RedisKey.API_CACHE`
- `RedisInitKeyConfig.API_RATE_LIMIT.key` → `RedisKey.API_RATE_LIMIT`

`cache_service.py` 中遍历枚举展示缓存名称列表的逻辑，SHALL 改为遍历 `RedisKey` 常量 + `CACHE_KEY_REMARKS` 映射。

`DistributedLockConstants`（`common/constant.py`）0 处业务引用，随 import 路径更新一并清理内部引用。

#### Scenario: 全项目无 RedisInitKeyConfig 残留
- **WHEN** 执行 `grep -r 'RedisInitKeyConfig'` 扫描全项目 `.py` 文件
- **THEN** SHALL 返回零匹配结果（枚举定义和所有引用均已删除）

#### Scenario: RedisKey 提供 remark 映射
- **WHEN** `cache_service.py` 需要展示缓存名称列表
- **THEN** `RedisKey` SHALL 提供 `CACHE_KEY_REMARKS` 常量映射（`{prefix: remark}`），替代原枚举的 `remark` 属性

### Requirement: 运行时行为不变
本次重构 SHALL 不改变任何 Redis 操作的运行时行为。所有 Redis 命令封装、Pub/Sub 监听循环、分布式锁获取/释放逻辑 SHALL 保持与重构前完全一致。

#### Scenario: RedisClient CRUD 行为一致
- **WHEN** 调用 `RedisClient.set('key', {'a': 1})` 后调用 `RedisClient.get('key')`
- **THEN** 返回值 SHALL 为 `{'a': 1}`，与重构前行为一致

#### Scenario: RedisPubSub 订阅行为一致
- **WHEN** 调用 `RedisPubSub.subscribe(channel, handler)` 后发布消息
- **THEN** handler SHALL 收到与重构前相同结构的 `PubSubMessage` 对象

#### Scenario: DistributedLock 锁行为一致
- **WHEN** 使用 `async with DistributedLock(key, expire=30) as acquired`
- **THEN** 锁获取、续期、释放逻辑 SHALL 与重构前完全一致
