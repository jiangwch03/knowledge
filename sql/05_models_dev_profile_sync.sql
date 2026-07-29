-- models.dev Profile 本地索引：每日同步定时任务
-- 幂等：按 invoke_target 去重

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'models.dev Profile 每日同步', 'default', 'default',
    'knowledge_admin.tasks.models_dev_profile_sync.sync_models_dev_profiles',
    '', '', '0 0 3 * * ?', '3', '1', '0', 'knowledge-admin',
    'admin', NOW(), 'admin', NOW(),
    '每天 03:00 拉取 models.dev/api.json，刷新本地 Profile 索引（按 model_code 查询，不依赖厂商 SDK）'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_admin.tasks.models_dev_profile_sync.sync_models_dev_profiles'
);
