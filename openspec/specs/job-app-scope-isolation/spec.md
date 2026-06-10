# Capability: job-app-scope-isolation

## Purpose

定时任务按 `app_scope` 字段在多项目之间隔离加载与同步：通过 admin 后台统一管理不同后端项目（admin / rag 等）的定时任务，各项目 Leader 仅加载属于自己的任务，跨项目变更通过 Redis 全局广播实时同步。

TBD

## Requirements

### Requirement: sys_job 表支持 app_scope 字段
`sys_job` 表 SHALL 包含 `app_scope` 字段（VARCHAR(64)，默认 `'knowledge-admin'`），用于标识任务所属应用。可选值为字典表 `sys_job_app_scope` 中维护的条目。

#### Scenario: 新增任务时指定 app_scope
- **WHEN** 用户在 admin 后台新增定时任务并选择 `app_scope = 'knowledge-admin'`
- **THEN** 任务记录的 `app_scope` 保存为 `'knowledge-admin'`

#### Scenario: 兼容旧数据
- **WHEN** 系统加载历史任务（`app_scope` 为 NULL 或空字符串）
- **THEN** 将其视为 `'knowledge-admin'`，由 admin 项目加载

### Requirement: sys_job_log 表支持 app_scope 字段
`sys_job_log` 表 SHALL 包含 `app_scope` 字段（VARCHAR(64)，默认 `'knowledge-admin'`），记录任务执行时所属的应用标识。

#### Scenario: 任务执行日志记录 app_scope
- **WHEN** 定时任务被执行并产生日志
- **THEN** 日志记录的 `app_scope` 与对应任务的 `app_scope` 一致

### Requirement: Scheduler 仅加载当前应用的任务
各后端项目启动时，Scheduler SHALL 只加载 `app_scope` 匹配当前应用标识的任务。admin 项目额外加载 `app_scope` 为 NULL/空值的历史任务。

#### Scenario: admin 项目启动
- **WHEN** admin 项目启动并成为 Leader
- **THEN** 仅加载 `app_scope` 为 `'knowledge-admin'` 或 NULL/空值的任务

#### Scenario: rag 项目启动
- **WHEN** rag 项目启动并成为 Leader
- **THEN** 仅加载 `app_scope` 为 `'knowledge-rag'` 的任务

### Requirement: 任务管理服务接收并保存 app_scope
通过 admin 后台管理（增/改/删）定时任务时，JobService SHALL 接收前端表单传入的 `app_scope` 并保存，保存成功后向全局广播频道发布同步通知。

#### Scenario: 新增任务时选择 app_scope
- **WHEN** 用户在 admin 后台新增定时任务并选择 `app_scope = 'knowledge-rag'`
- **THEN** 任务记录的 `app_scope` 保存为 `'knowledge-rag'`，admin 向全局频道广播同步通知

#### Scenario: 编辑任务时修改 app_scope
- **WHEN** 用户编辑已有任务并修改 `app_scope`
- **THEN** 更新后的 `app_scope` 保存到数据库，admin 向全局频道广播同步通知，各项目 Leader 收到后各自同步

### Requirement: 跨项目全局广播同步
admin 后台增/改/删定时任务后，系统 SHALL 通过 Redis 全局频道 `scheduler:global:sync` 广播通知，消息体 SHALL 包含 `app_scope`。各后端项目的 Leader 收到后，只有 `app_scope` 匹配自身或消息未指定 `app_scope` 时才触发同步。

#### Scenario: admin 新增 rag 任务后 rag 实时感知
- **WHEN** admin 后台新增一个 `app_scope = 'knowledge-rag'` 的任务
- **THEN** admin 向 `scheduler:global:sync` 频道广播，消息体包含 `app_scope = 'knowledge-rag'`
- **THEN** rag 的 Leader 收到通知，匹配 `app_scope`，立即从数据库同步加载该新任务
- **THEN** admin 的 Leader 收到通知，`app_scope` 不匹配，跳过同步

#### Scenario: admin 停用任务后目标项目实时感知
- **WHEN** admin 后台停用（status='1'）一个 `app_scope = 'knowledge-rag'` 的任务
- **THEN** admin 向全局频道广播，消息体包含 `app_scope = 'knowledge-rag'`
- **THEN** rag 的 Leader 收到通知后同步，从 Scheduler 中移除该任务
- **THEN** admin 的 Leader 收到通知后跳过

### Requirement: 前端支持 app_scope 筛选和展示
前端任务管理页面 SHALL 支持按 `app_scope` 筛选任务，并在列表中展示该字段。

#### Scenario: 筛选 admin 任务
- **WHEN** 用户在任务列表选择 `app_scope = knowledge-admin`
- **THEN** 仅展示 `app_scope` 为 `'knowledge-admin'` 或 NULL/空值的任务

#### Scenario: 列表展示 app_scope
- **WHEN** 用户查看定时任务列表
- **THEN** 列表中包含 `app_scope` 列