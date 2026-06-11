## Why

Redis 相关基础设施代码散落在 `utils/`、`common/`、`config/` 三个目录共 5 个文件中，存在 JSON 序列化逻辑重复、命名风格不统一等问题。随着 Redis 能力持续增长（CRUD、Pub/Sub、分布式锁、Stream、Broadcast），缺乏统一包边界导致新开发者难以定位代码，维护成本上升。

## What Changes

- 新建 `knowledge_common/redis/` 包，将散落在 3 个目录的 Redis 能力文件归拢为单一模块
- 统一 JSON 序列化/反序列化逻辑到 `redis/serialization.py`，消除 `redis_client.py`、`redis_pubsub_util.py` 中的重复实现
- 全量改造所有旧路径导入引用到新包路径，旧文件直接删除，不留兼容 re-export 层
- 清理废弃 `RedisInitKeyConfig` 枚举（25+ 处替换为 `RedisKey` 常量），统一 Key 体系
- **不移动** `RedisContext`（保留在 `common/context.py`）和 `RedisContextMiddleware`（保留在 `middlewares/redis_context_middleware.py`）：它们是项目级上下文管理机制，不属于 Redis 能力范畴
- **不移动** `broadcast/backends/redis_pubsub.py` 和 `message_stream/backends/redis_stream.py`：它们属于各自服务框架的后端实现，职责边界清晰

## Capabilities

### New Capabilities
- `redis-package-restructure`: 将 Redis 能力文件（Key 定义、连接池、CRUD 封装、Pub/Sub 工具、分布式锁）归拢到 `knowledge_common/redis/` 统一包，提取公共序列化逻辑，全量改造所有导入路径

### Modified Capabilities
<!-- 无需修改现有 spec 的需求级别行为 -->

## Impact

- **涉及文件**：`common/redis_key.py`、`config/get_redis.py`、`utils/redis_client.py`、`utils/redis_pubsub_util.py`、`utils/distributed_lock.py`（迁移后删除）
- **不移动**：`common/context.py`（`RedisContext`）、`middlewares/redis_context_middleware.py`（`RedisContextMiddleware`）— 项目级上下文管理，非 Redis 能力
- **导入改造**：全项目 grep 所有旧路径引用，统一替换为 `knowledge_common.redis.*` 新路径（涉及 `knowledge-common`、`knowledge-admin`、`knowledge-rag` 三个子项目）
- **Key 清理**：`RedisInitKeyConfig` 废弃枚举 25+ 处全量替换为 `RedisKey` 常量（涉及 6 个文件），删除枚举定义
- **依赖关系**：`broadcast/backends/`、`message_stream/backends/` 不受影响，仍通过 `RedisContext` 获取客户端
- **测试**：现有测试无需修改（类对象不变，仅导入路径变更）
