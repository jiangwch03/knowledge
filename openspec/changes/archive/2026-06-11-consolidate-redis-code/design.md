## Context

项目 Redis 相关代码按职责应分三层，但现状是职责越界和重复实现并存：

**基础设施层**（连接、上下文、Key 定义）：

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `config/get_redis.py` (`RedisUtil`) | 142 | 连接池+启动缓存 | `init_sys_dict`/`init_sys_config` 是业务级缓存预热，不属于连接管理 |
| `common/redis_key.py` | 120 | Key 定义 | 无 |

**Key 使用现状**（两套并存）：

| 定义 | 状态 | 活跃使用处 | 说明 |
|------|------|-----------|------|
| `RedisKey` / `LockKey` | 推荐 | 3 处导入（`enums.py` docstring、`constant.py`、`distributed_lock.py` docstring） | 新代码应使用 |
| `RedisInitKeyConfig`（枚举） | 已标注废弃 | 6 个文件 25+ 处（`cache_annotation`、`rate_limit_annotation`、`login_user_service`、`config_service`、`dict_service`、`cache_service`） | 实际未迁移，仍为主力 |
| `DistributedLockConstants` | 已标注废弃 | 0 处业务引用 | 仅 docstring 示例 |

**能力层**（CRUD、Pub/Sub、分布式锁）：

| 文件 | 行数 | 职责 | 问题 |
|------|------|------|------|
| `utils/redis_client.py` (`RedisClient`) | 584 | CRUD + 透明序列化 | 无 |
| `utils/redis_pubsub_util.py` (`RedisPubSubUtil`) | 412 | Pub/Sub + 自动重连 | 类名 Util 后缀多余 |
| `utils/distributed_lock.py` (`DistributedLock`) | 215 | 分布式锁 + 续期 | 无 |

**框架层**（BroadcastService、MessageStreamService）— 不受影响：
- `broadcast/backends/redis_pubsub.py` — BroadcastService 后端，职责边界清晰
- `message_stream/backends/redis_stream.py` — MessageStreamService 后端，Stream 协议独立

其他不受影响：`common/context.py`（`RedisContext`）和 `middlewares/redis_context_middleware.py`（`RedisContextMiddleware`）是项目级上下文管理机制，非 Redis 能力，保留原位。

## Goals / Non-Goals

**Goals:**
- 将 5 个 Redis 能力文件归拢到 `knowledge_common/redis/` 统一包
- 拆分 `RedisUtil` 职责：`init_sys_dict`/`init_sys_config` 回归 Service 层，连接管理器只管连接
- 提取公共 JSON 序列化逻辑到 `redis/serialization.py`
- 清理类名：`RedisUtil` → `RedisConnection`，`RedisPubSubUtil` → `RedisPubSub`
- 全量改造所有旧路径导入引用到新包路径，旧文件直接删除，风格统一
- 清理废弃 Key 枚举：`RedisInitKeyConfig` 全部替换为 `RedisKey` 常量，删除废弃枚举类

**Non-Goals:**
- 不移动 `RedisContext`（保留在 `common/context.py`）和 `RedisContextMiddleware`（保留在 `middlewares/`）
- 不重构 `broadcast/` 和 `message_stream/` 的后端实现
- 不改变任何 Redis 操作的运行时行为
- 不合并 `RedisPubSubUtil` 与 `RedisPubSubBackend` 的 listen loop（两者服务于不同抽象层级，暂不统一）
- 不新增 Redis 功能

## Decisions

### Decision 1: 新建 `knowledge_common/redis/` 包

**选择**：新建顶级 `redis/` 包

**理由**：Redis 能力已涵盖 Key 定义、连接池、CRUD、Pub/Sub、分布式锁 5 个子模块，体量远超普通 util。独立包提供清晰的边界，一个包即一个能力域。

### Decision 2: 拆分 RedisUtil 职责

**选择**：`init_sys_dict`/`init_sys_config` 从 `RedisUtil` 移出，回归 `DictDataService`/`ConfigService`

**理由**：这两个方法是业务级缓存预热逻辑（调用 Service 层从数据库加载数据到 Redis），不属于连接池生命周期管理。混在连接管理器中违反单一职责原则。重构后 `RedisConnection` 只管连接的创建、健康检查、关闭。

**替代方案**：保留在 connection.py 但重命名为 `startup_cache_init`。但这仍会让连接管理器依赖 Service 层，方向不对。

### Decision 3: 清理类名

| 当前 | 新名 | 理由 |
|------|------|------|
| `RedisUtil` | `RedisConnection` | 去掉 Util 后缀，明确表达连接管理职责 |
| `RedisPubSubUtil` | `RedisPubSub` | 去掉 Util 后缀，类名即能力名 |
| `RedisContextMiddleware` | 保持不变，保留在 `middlewares/` | ASGI 中间件属项目基础设施层，非 Redis 能力 |
| `RedisClient` | 保持不变 | 名称清晰 |
| `DistributedLock` | 保持不变 | 名称清晰 |

### Decision 4: 包内文件结构

```
knowledge_common/redis/
├── __init__.py              # 统一 re-export 入口
├── key.py                   # RedisKey + LockKey
├── connection.py            # RedisConnection（原 RedisUtil，去掉 init_sys_*）
├── client.py                # RedisClient CRUD
├── pubsub.py                # RedisPubSub（原 RedisPubSubUtil）
├── lock.py                  # DistributedLock
└── serialization.py         # 公共 JSON 序列化/反序列化
```

`RedisContextMiddleware` 保留在 `middlewares/redis_context_middleware.py`，不纳入 `redis/` 包。

### Decision 5: 序列化逻辑提取为独立模块

**选择**：新建 `redis/serialization.py`，提供 `serialize`/`deserialize`/`encode_payload`/`decode_message_data`

**理由**：`redis_client.py` 和 `redis_pubsub_util.py` 存在重复的 JSON 处理逻辑。提取后两者均调用同一实现。

**不纳入**：`broadcast/backends/redis_pubsub.py` 和 `message_stream/backends/redis_stream.py` 的序列化逻辑——它们处理的是 Redis 原始 bytes/str 差异和 Stream fields 特殊协议，语义不同。

### Decision 6: 全量改造导入路径，旧文件直接删除

**选择**：迁移完成后全项目 grep 替换所有旧路径，然后删除旧文件

**理由**：项目仅 3 个子包，旧路径引用约 13 处，全量改造一步到位，风格统一无历史包袱。

### Decision 7: 清理废弃 `RedisInitKeyConfig` 枚举

**选择**：将所有 `RedisInitKeyConfig.XXX.key` 替换为 `RedisKey.XXX`，删除 `RedisInitKeyConfig` 枚举类

**理由**：`RedisInitKeyConfig` 已标注"废弃，请用 `RedisKey`"，但 25+ 处业务代码从未实际迁移。本次重构统一 Key 体系，消除两套并存的混乱。

**替换映射**：
```
RedisInitKeyConfig.ACCESS_TOKEN.key  →  RedisKey.ACCESS_TOKEN
RedisInitKeyConfig.SYS_DICT.key      →  RedisKey.SYS_DICT
RedisInitKeyConfig.SYS_CONFIG.key    →  RedisKey.SYS_CONFIG
RedisInitKeyConfig.API_CACHE.key     →  RedisKey.API_CACHE
RedisInitKeyConfig.API_RATE_LIMIT.key → RedisKey.API_RATE_LIMIT
```

**涉及文件**（6 个）：
- `common/annotation/cache_annotation.py`（3 处）
- `common/annotation/rate_limit_annotation.py`（1 处）
- `service/login_user_service.py`（5 处）
- `service/config_service.py`（7 处）
- `service/dict_service.py`（2 处）
- `knowledge-admin/service/cache_service.py`（遍历枚举值，需改为遍历 `RedisKey` 常量）

**`cache_service.py` 特殊处理**：该文件遍历 `RedisInitKeyConfig` 枚举展示缓存名称列表（含 `remark` 展示名）。替换方案：在 `RedisKey` 上增加 `CACHE_KEY_REMARKS: dict[str, str]` 常量映射，供缓存监控 UI 使用。

**`DistributedLockConstants`**：0 处业务引用，随 `constant.py` 内部 import 路径更新一并清理。

## Risks / Trade-offs

- **[init_sys_* 迁移]** → `init_sys_dict`/`init_sys_config` 移出后，调用方（`server.py`、`cache_service.py`）需改为直接调用 `DictDataService.init_cache()`/`ConfigService.init_cache()`。需确认 Service 层已有对应方法或新增。
- **[循环导入]** → `redis/connection.py` 移出 `init_sys_*` 后不再依赖 Service 层，循环导入风险降低。
- **[导入遗漏]** → 通过全项目 `grep -r` 扫描所有旧路径引用，确保无遗漏。
- **[git 历史丢失]** → 文件搬迁会导致 git blame 历史断裂。通过 `git mv` 保留可追踪历史。
- **[RedisInitKeyConfig 遗漏]** → 25+ 处替换量大，通过 `grep -r 'RedisInitKeyConfig'` 确保零残留。`cache_service.py` 遍历枚举的逻辑需特殊处理（改为遍历 `RedisKey` 常量 + `CACHE_KEY_REMARKS`）。
