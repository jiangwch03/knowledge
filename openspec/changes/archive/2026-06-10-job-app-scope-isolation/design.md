## Context

当前项目的定时任务调度基于 `APScheduler` + 共享数据库表 `sys_job`。

- `knowledge-common` 提供 `SchedulerUtil`，是一个单例类，管理全局 `AsyncIOScheduler` 实例
- `knowledge-admin` 和 `knowledge-content` 两个后端项目各自在 `server.py` 中调用 `SchedulerUtil.init_system_scheduler()`
- 两个项目使用不同的 Redis 锁键（基于 `APP_NAME`），因此各自独立选举 Leader，互不干扰
- 但 `sys_job` 表没有项目归属字段，两个 Leader 都会加载表中全部任务
- 由于 admin 和 rag 是独立进程，各自只包含自己的 Python 包，一方的任务代码在另一方进程中无法导入

## Goals / Non-Goals

**Goals:**
- 让 admin 和 rag 两个后端项目能够独立运行各自的定时任务代码，互不干扰
- 保留在 admin 后台统一管理所有任务的能力
- 兼容历史数据，不强制迁移

**Non-Goals:**
- 修改 APScheduler 底层机制或替换调度框架
- 让两个项目共享执行同一个任务（这本来就由 Leader 单点执行）
- 修改 Redis 分布式锁机制

## Decisions

### 1. 新增 `app_scope` 字段而非利用 `job_group`
**选择**：在 `sys_job` 和 `sys_job_log` 中新增 `app_scope` 字段  
**理由**：`job_group` 已被用于 APScheduler 的 jobstore 分组（如 `default`/`sqlalchemy`/`redis`），语义上表示存储后端而非应用归属。混用会导致概念混乱。

### 2. 默认值为 `'knowledge-admin'`，可选值由字典表维护
**选择**：`sys_job`/`sys_job_log` 的 `app_scope` 字段默认 `'knowledge-admin'`，NULL/空值也视为 `'knowledge-admin'`。可选值列表（`knowledge-admin`、`knowledge-content`、`knowledge-agent`）通过 `sys_dict_type` + `sys_dict_data` 字典表维护。  
**理由**：
- 兼容旧数据：历史任务默认归属 admin（管理后台），由 admin 项目加载，行为与改造前一致
- 项目名称即字典值，避免硬编码枚举，便于扩展（如新增 `knowledge-agent`）
- 字典表已有成熟的前端下拉组件支持，无需额外开发

### 3. 前端表单传参，后端接收保存
**选择**：`app_scope` 由前端表单下拉框传入，后端 `JobService` 直接接收并保存  
**理由**：
- 前端只有一套（knowledge-web），任务管理页面统一在 admin 后台
- 运维人员需要在同一个管理界面中为不同后端项目（admin/rag/agent）创建各自的定时任务
- 下拉框值从字典接口（`sys_job_app_scope`）动态获取，避免硬编码
- 项目为内部管理平台（非 toC），前端伪造风险可控

### 4. `SchedulerUtil` 启动时传入应用标识
**选择**：改造 `init_system_scheduler` 的签名，接收当前应用标识（如 `'knowledge-admin'`/`'knowledge-content'`）  
**理由**：SchedulerUtil 位于 `knowledge-common`，本身不知道自己是被哪个项目调用的。由调用方（`server.py`）传入最合理。

### 7. 跨项目全局广播同步机制
**选择**：新增 Redis 全局广播频道 `scheduler:global:sync`，admin 后台增/改/删任务后向该频道广播，消息体携带 `app_scope`。所有项目的 Leader 订阅该频道，收到后判断 `app_scope` 是否匹配自身，匹配才触发同步。  
**理由**：
- 任务管理统一在 admin 后台，但 rag 的 Leader 需要实时感知属于自己任务的变更
- 广播消息携带 `app_scope`，非目标项目的 Leader 直接跳过，避免无效查库
- 全局广播保持各项目 Scheduler 独立，只同步属于自己的任务，互不干扰
- 废弃原有进程内同步机制（`_sync_channel`），统一用全局频道，代码更简洁

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|---------|
| 旧任务被两边重复执行的问题未解决（如果旧任务实际只属于一个项目） | 属于已知现状，`knowledge-admin` 默认行为保持一致；如需隔离，需手动修改 `app_scope` |
| 前端增加 `app_scope` 列后列表变宽 | 可在小屏下隐藏或使用 tooltip |
| 前端下拉框误选导致任务归属错误 | 属于人为操作风险，内部平台可控；下拉框默认值设为 `knowledge-admin`，减少误操作 |

## Migration Plan

1. 执行数据库 ALTER 语句添加 `app_scope` 字段（默认 `'knowledge-admin'`）
2. 更新 SQL 初始化脚本 `sql/ruoyi-fastapi.sql`（含 `sys_job`、`sys_job_log` 字段 + `sys_dict_type`/`sys_dict_data` 字典数据）
3. 确认 `knowledge-common` 中通用字典查询方法满足需求（`DictDataService.query_dict_data_list_from_cache_services`）
4. 废弃 `_sync_channel` 及进程内监听器，统一为全局广播频道
5. 部署新版后端代码（admin 和 rag 都需重启）
6. 如有需要，手动将已有任务更新为正确的 `app_scope`

无需回滚策略：新增字段和过滤逻辑都是向后兼容的，回退旧版本只需忽略该字段即可。

## Open Questions

- 前端 `app_scope` 下拉框是否需要在编辑时禁用（防止运行中的任务被误改归属）？
- `app_scope` 是否需要支持多个值（如 `'knowledge-admin,knowledge-content'`）？当前设计不支持，如有需求可后续扩展。

### 5. 用字典表维护 `app_scope` 可选值
**选择**：在 `sys_dict_type` 新增 `sys_job_app_scope` 类型，在 `sys_dict_data` 中插入 `knowledge-admin`、`knowledge-content`、`knowledge-agent` 三条数据。  
**理由**：项目名称作为字典值，前端可直接复用现有字典下拉组件；新增项目时只需插入字典数据，无需改代码。

### 6. 复用/增强 common 字典查询方法
**选择**：复用 `DictDataService.query_dict_data_list_from_cache_services(redis, dict_type)` 从 Redis 缓存获取字典列表；如需只取 `dict_value` 值列表，可封装便捷方法。  
**理由**：该方法已存在且被多处使用，前端下拉框可直接调用现有字典接口获取 `sys_job_app_scope` 的选项列表。
