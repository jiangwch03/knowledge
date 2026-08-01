-- =============================================================================
-- 04_upgrade_proxy_pool_sync.sql
-- 爬虫代理池：拉取（2 分钟，只增）+ 清理（1 分钟，只删）两个定时任务
-- 依赖：02 已初始化 sys_dict_type.crawl_proxy_pool；knowledge-content 已部署任务代码
-- 可重复执行
-- =============================================================================

-- 移除早期合并版单任务（若存在）
DELETE FROM `sys_job`
WHERE `invoke_target` = 'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_job';

-- 拉取：每 2 分钟只新增字典中尚不存在的代理
INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '爬虫代理池拉取', 'default', 'default',
    'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_fetch_job',
    '', '', '0 0/2 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(),
    '每2分钟从 proxy_pool API(/all) 拉取；丢弃 last_status=false，排除字典已有 server，只插入新增并刷新缓存'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_fetch_job'
);

UPDATE `sys_job`
SET `remark` = '每2分钟从 proxy_pool API(/all) 拉取；丢弃 last_status=false，排除字典已有 server，只插入新增并刷新缓存',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `invoke_target` = 'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_fetch_job';

-- 清理：每 1 分钟探测字典节点，只删不通
INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '爬虫代理池清理', 'default', 'default',
    'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_cleanup_job',
    '', '', '0 * * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(),
    '每1分钟对 crawl_proxy_pool 字典节点做存活探测，只删除不通项并刷新缓存；可选回调源池 /delete'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_cleanup_job'
);

UPDATE `sys_job`
SET `remark` = '每1分钟对 crawl_proxy_pool 字典节点做存活探测，只删除不通项并刷新缓存；可选回调源池 /delete',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `invoke_target` = 'knowledge_content.tasks.proxy_pool_sync_scheduler.sync_proxy_pool_cleanup_job';
