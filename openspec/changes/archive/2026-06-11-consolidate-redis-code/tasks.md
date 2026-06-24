## 1. 创建 redis/ 包基础结构

- [x] 1.1 创建 `knowledge_common/redis/` 目录和 `__init__.py`
- [x] 1.2 创建 `redis/serialization.py`：提取 `serialize()`、`deserialize()`、`encode_payload()`、`decode_message_data()` 公共函数

## 2. 迁移连接池管理 + 拆分职责

- [x] 2.1 将 `config/get_redis.py` 中连接池方法（`create_redis_pool`、`close_redis_pool`、`check_redis_connection`、`get_redis`）复制到 `redis/connection.py`，类名改为 `RedisConnection`，移除 `init_sys_dict`/`init_sys_config`
- [x] 2.2 将 `init_sys_dict` 逻辑回归 `DictDataService`（新增或确认已有 `init_cache` 方法）
- [x] 2.3 将 `init_sys_config` 逻辑回归 `ConfigService`（新增或确认已有 `init_cache` 方法）

## 3. 迁移 Key 定义

- [x] 3.1 将 `common/redis_key.py` 内容（`RedisKey` + `LockKey`）复制到 `redis/key.py`，更新内部导入路径
- [x] 3.2 在 `redis/key.py` 的 `RedisKey` 中增加 `CACHE_KEY_REMARKS: dict[str, str]` 常量映射（供缓存监控 UI 替代原 `RedisInitKeyConfig.remark`）

## 4. 迁移 CRUD 封装

- [x] 4.1 将 `utils/redis_client.py` 内容（`RedisClient`）复制到 `redis/client.py`，将内部 `_serialize/_deserialize` 替换为调用 `redis.serialization`

## 5. 迁移 Pub/Sub 工具 + 重命名

- [x] 5.1 将 `utils/redis_pubsub_util.py` 内容复制到 `redis/pubsub.py`，类名改为 `RedisPubSub`，将内部 `_encode_payload/_parse_message` 替换为调用 `redis.serialization`

## 6. 迁移分布式锁

- [x] 6.1 将 `utils/distributed_lock.py` 内容（`DistributedLock`）复制到 `redis/lock.py`，更新导入路径使用 `common.context.RedisContext` 和 `redis.key.LockKey`

## 7. 统一包入口

- [x] 7.1 编写 `redis/__init__.py`：re-export 所有公开类（`RedisKey`、`LockKey`、`RedisConnection`、`RedisClient`、`RedisPubSub`、`PubSubMessage`、`DistributedLock`）

## 8. 全量改造导入路径

- [x] 8.1 改造 `knowledge-common` 内部引用：`middlewares/handle.py`、`config/get_scheduler.py`、`common/constant.py`、`common/enums.py`
- [x] 8.2 改造 `knowledge-admin` 引用：`server/server.py`、`service/cache_service.py`（`RedisUtil` → `RedisConnection`，`init_sys_*` → Service 层调用）
- [x] 8.3 改造 `knowledge-content` 引用：`server/server.py`（`RedisUtil` → `RedisConnection`，`init_sys_*` → Service 层调用）

## 9. 清理废弃 RedisInitKeyConfig 枚举

- [x] 9.1 替换 `common/annotation/cache_annotation.py`：`RedisInitKeyConfig.API_CACHE.key` → `RedisKey.API_CACHE`（3 处）
- [x] 9.2 替换 `common/annotation/rate_limit_annotation.py`：`RedisInitKeyConfig.API_RATE_LIMIT.key` → `RedisKey.API_RATE_LIMIT`（1 处）
- [x] 9.3 替换 `service/login_user_service.py`：`RedisInitKeyConfig.ACCESS_TOKEN.key` / `SYS_CONFIG.key` → `RedisKey.ACCESS_TOKEN` / `RedisKey.SYS_CONFIG`（5 处）
- [x] 9.4 替换 `service/config_service.py`：`RedisInitKeyConfig.SYS_CONFIG.key` → `RedisKey.SYS_CONFIG`（7 处）
- [x] 9.5 替换 `service/dict_service.py`：`RedisInitKeyConfig.SYS_DICT.key` → `RedisKey.SYS_DICT`（2 处）
- [x] 9.6 改造 `knowledge-admin/service/cache_service.py`：遍历枚举值改为遍历 `RedisKey.CACHE_KEY_REMARKS`
- [x] 9.7 删除 `common/enums.py` 中 `RedisInitKeyConfig` 枚举类定义及其导入
- [x] 9.8 清理 `common/constant.py` 中 `DistributedLockConstants` 对 `LockKey` 的废弃引用，更新为新路径

## 10. 删除旧文件

- [x] 10.1 删除旧文件：`utils/redis_client.py`、`utils/redis_pubsub_util.py`、`utils/distributed_lock.py`、`common/redis_key.py`、`config/get_redis.py`

## 11. 验证

- [x] 11.1 全项目 grep 扫描确认无旧路径残留（`knowledge_common.utils.redis_client` 等 5 条旧路径）
- [x] 11.2 全项目 grep 扫描确认无 `RedisInitKeyConfig` 残留
- [x] 11.3 Python import 验证：确认所有新路径均可正常导入
- [x] 11.4 运行现有测试套件确认无回归（138 passed, 5 skipped）

## 12. 额外修复（实施中发现）

- [x] 12.1 修复 `knowledge-admin/controller/login_controller.py`：`RedisInitKeyConfig` → `RedisKey`
- [x] 12.2 修复 `knowledge-admin/controller/captcha_controller.py`：`RedisInitKeyConfig` → `RedisKey`
- [x] 12.3 修复 `knowledge-admin/service/login_service.py`：`RedisInitKeyConfig` → `RedisKey`
- [x] 12.4 修复 `knowledge-admin/service/online_service.py`：`RedisInitKeyConfig` → `RedisKey`
- [x] 12.5 修复 `middlewares/redis_context_middleware.py` docstring：`RedisPubSubUtil` → `RedisPubSub`
- [x] 12.6 修复 `common/context.py` 错误消息：`RedisUtil` → `RedisConnection`
