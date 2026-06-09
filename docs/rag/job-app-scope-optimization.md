# 定时任务多项目运行支持优化说明

## 原方案存在的两个问题

### 问题 1：无法适配多个后端项目运行各自的定时任务

当前项目基于 APScheduler + 共享 `sys_job` 表实现定时任务调度。`knowledge-admin` 和 `knowledge-rag` 两个后端项目各自运行独立进程，且各自选举 Leader 启动 Scheduler。但由于 `sys_job` 表没有项目归属字段，两个项目的 Leader 都会加载表中全部任务，导致：

- admin 进程尝试加载 rag 专属任务（如 `knowledge_rag.tasks.xxx`）时发生 `ModuleNotFoundError`
- rag 进程尝试加载 admin 专属任务（如 `knowledge_admin.tasks.xxx`）时同样导入失败

**结果**：两个后端项目无法真正独立运行各自的定时任务代码，任何一方新增任务都可能导致另一方启动失败。

### 问题 2：缺少全局广播机制，任务变更同步严重滞后

任务管理统一在 admin 后台入口，但 admin 增/改/删任务后，rag 进程完全感知不到变更：

- rag 只有在**重启**时才能从数据库加载最新任务
- 自动轮询间隔为 **30 秒**，任务停用/删除的延迟可能导致多执行一次
- 生产环境中，任务重复执行或延迟停止可能造成重大损失

**结果**：缺乏跨项目的实时同步机制，无法保证任务状态的一致性。

---

## 改造方案

### 针对问题 1：新增 `app_scope` 字段实现任务隔离

在 `sys_job` 和 `sys_job_log` 表中新增 `app_scope` 字段，标识任务所属应用：

| 字段值 | 说明 | 加载方 |
|--------|------|--------|
| `knowledge-admin` | 管理后台专属任务 | admin 项目 |
| `knowledge-rag` | RAG 服务专属任务 | rag 项目 |
| `knowledge-agent` | Agent 服务专属任务 | agent 项目 |

**核心改动**：
- `sys_job`/`sys_job_log` 表新增 `app_scope` 字段，默认 `'knowledge-admin'`
- `SchedulerUtil.init_system_scheduler` 增加 `app_scope` 参数，各项目启动时传入自身标识
- `_sync_jobs_from_database` 仅加载匹配当前 `app_scope` 的任务（admin 额外兼容 NULL 值历史任务）
- 可选值通过 `sys_dict_type`/`sys_dict_data` 字典表维护，便于前端复用和扩展

### 针对问题 2：全局广播同步机制替代进程内同步

废弃原有 `_sync_channel` 进程内同步机制，统一采用 Redis 全局广播：

```
admin 后台增/改/删任务 → 保存到数据库
                              │
                              ▼
            SchedulerUtil.broadcast_scheduler_sync(app_scope='knowledge-rag')
                              │
                              ▼
            Redis Publish: scheduler:global:sync
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         admin Leader    rag Leader      knowledge-agent Leader
              │               │               │
              ▼               ▼               ▼
         app_scope 不匹配   app_scope 匹配    app_scope 不匹配
         跳过同步          触发同步           跳过同步
```

**核心改动**：
- 新增全局广播频道 `scheduler:global:sync`，消息体携带 `app_scope`
- 各项目 Leader 订阅该频道，收到后判断 `app_scope` 匹配才触发同步
- 自动轮询间隔从 **30 秒**缩短至 **10 秒**，作为兜底策略
- `JobService` 增/改/删任务后调用广播，目标项目实时感知

---

## 收益

- **任务隔离**：admin 和 rag 各自只加载和执行属于自己的定时任务，互不干扰
- **实时同步**：admin 后台操作后，目标项目 Leader 实时感知并同步，消除延迟
- **统一管理**：运维人员可在同一界面管理所有项目的定时任务
- **向后兼容**：历史任务默认归属 admin，无需强制迁移
