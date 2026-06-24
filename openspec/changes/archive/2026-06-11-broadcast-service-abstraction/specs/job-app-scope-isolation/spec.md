## MODIFIED Requirements

### Requirement: 跨项目全局广播同步
admin 后台增/改/删定时任务后，系统 SHALL 通过 `BroadcastService.publish()` 向 `scheduler:global:sync` channel 发布同步通知，消息体 SHALL 包含 `app_scope`。各后端项目的 Leader 通过 `@subscriber` 装饰器声明的 handler 接收消息，只有 `app_scope` 匹配自身或消息未指定 `app_scope` 时才触发同步。

#### Scenario: admin 新增 rag 任务后 rag 实时感知
- **WHEN** admin 后台新增一个 `app_scope = 'knowledge-content'` 的任务
- **THEN** admin 通过 `BroadcastService.publish()` 向 `scheduler:global:sync` channel 发布消息，消息体包含 `app_scope = 'knowledge-content'`
- **THEN** rag 的 Leader 通过 `@subscriber` handler 收到通知，匹配 `app_scope`，立即从数据库同步加载该新任务
- **THEN** admin 的 Leader handler 收到通知，`app_scope` 不匹配，跳过同步

#### Scenario: admin 停用任务后目标项目实时感知
- **WHEN** admin 后台停用（status='1'）一个 `app_scope = 'knowledge-content'` 的任务
- **THEN** admin 通过 `BroadcastService.publish()` 向全局 channel 发布消息
- **THEN** rag 的 Leader handler 收到通知后同步，从 Scheduler 中移除该任务
- **THEN** admin 的 Leader handler 收到通知后跳过
