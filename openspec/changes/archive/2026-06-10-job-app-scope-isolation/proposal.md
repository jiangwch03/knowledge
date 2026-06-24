## Why

当前项目的定时任务调度机制基于 APScheduler + 共享 `sys_job` 表，admin 和 rag 两个后端项目各自运行独立的进程，且各自选举 Leader 启动 Scheduler。但由于 `sys_job` 表没有项目归属字段，两个项目的 Leader 都会加载表中全部任务，导致：

1. admin 进程尝试加载 rag 专属任务（`knowledge_content.tasks.xxx`）时发生 `ModuleNotFoundError`
2. rag 进程尝试加载 admin 专属任务（`knowledge_admin.tasks.xxx`）时同样导入失败

这使得两个后端项目无法真正独立运行各自的定时任务代码。

## What Changes

- **BREAKING** `sys_job` 表新增 `app_scope` 字段（VARCHAR），标识任务所属应用（`knowledge-admin`/`knowledge-content`/`knowledge-agent`）
- `sys_job_log` 表同步增加 `app_scope` 字段，确保日志归属清晰
- `JobDao` 增加按 `app_scope` 过滤的查询方法，替换全表扫描
- `SchedulerUtil` 启动时传入当前应用标识，仅加载属于本应用的任务
- `JobService` 增/改/删任务时接收并保存前端表单传入的 `app_scope`，保存成功后向 Redis 全局频道广播同步通知，消息体携带 `app_scope`
- 各后端项目的 Leader 订阅全局广播频道，收到通知后根据 `app_scope` 判断是否触发同步
- 前端任务管理页面增加 `app_scope` 筛选和展示
- `sys_dict_type`/`sys_dict_data` 字典表新增 `sys_job_app_scope` 类型，SQL 脚本初始化三个可选值
- 在 `knowledge-common` 中新增根据字典类型查询字典值列表的通用方法
- 兼容旧数据：未设置 `app_scope` 的历史任务默认视为 `knowledge-admin`（由 admin 项目加载）

## Capabilities

### New Capabilities
- `job-app-scope-isolation`: 定时任务按应用隔离，各项目独立加载和运行属于自己的任务

### Modified Capabilities
- （无现有相关 spec 需要修改）

## Impact

- **数据库**：`sys_job`、`sys_job_log` 需新增字段，需同步更新 SQL 初始化脚本
- **后端**：`knowledge-common` 的 DAO、Service、SchedulerUtil 均需调整；`knowledge-admin` 的 JobController 可能需要调整入参
- **前端**：`knowledge-web` 的任务管理列表需增加 `app_scope` 列和筛选器
- **兼容性**：旧数据无需迁移，默认 `knowledge-admin` 值由 admin 项目加载
