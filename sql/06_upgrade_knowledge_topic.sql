-- =============================================================================
-- 06_upgrade_knowledge_topic.sql
-- 知识检索主题：主题表、关键词表、主题管理菜单
-- 可重复执行
-- =============================================================================

CREATE TABLE IF NOT EXISTS `knowledge_retrieve_topic` (
    `topic_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `topic_name` varchar(64) NOT NULL COMMENT '主题名称，未删除范围内唯一',
    `description` varchar(1000) DEFAULT NULL COMMENT '主题描述，最多1000字',
    `task_id` bigint NOT NULL COMMENT '抽词所用的切分任务',
    `doc_id` bigint NOT NULL COMMENT '切分任务所属文档',
    `keyword_limit` int NOT NULL COMMENT '关键词上限，仅允许 30/50/100/150/200',
    `keyword_count` int NOT NULL DEFAULT 0 COMMENT '当前未删除关键词数',
    `status` varchar(32) NOT NULL DEFAULT 'READY' COMMENT 'GENERATING生成中 READY已完成 FAILED失败',
    `keep_keywords` char(1) NOT NULL DEFAULT '0' COMMENT '本次抽词是否保留旧关键词（0否 1是）',
    `error_message` varchar(2000) DEFAULT NULL COMMENT '抽词失败原因',
    `user_id` bigint DEFAULT NULL COMMENT '归属用户',
    `dept_id` bigint DEFAULT NULL COMMENT '归属部门',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0存在 2删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`topic_id`),
    KEY `idx_topic_name` (`topic_name`),
    KEY `idx_task_id` (`task_id`),
    KEY `idx_del_flag` (`del_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识检索主题';

CREATE TABLE IF NOT EXISTS `knowledge_retrieve_topic_keyword` (
    `keyword_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `topic_id` bigint NOT NULL COMMENT '所属主题',
    `keyword` varchar(128) NOT NULL COMMENT '关键词',
    `weight` double NOT NULL DEFAULT 0 COMMENT 'extract_tags 权重',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0存在 2删除）',
    PRIMARY KEY (`keyword_id`),
    KEY `idx_topic_id` (`topic_id`),
    KEY `idx_topic_keyword` (`topic_id`, `keyword`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识检索主题关键词';

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '主题管理',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0' LIMIT 1),
       '8', 'topic', 'knowledge/topic/index', '', '',
       1, 0, 'C', '0', '0', 'rag:topic:list', 'tree',
       'admin', NOW(), 'admin', NOW(), '知识检索主题管理'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:topic:list' AND `menu_type` = 'C'
);

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '主题查询',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:topic:list' AND `menu_type` = 'C' LIMIT 1),
       '1', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:topic:query', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:topic:query');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '主题新增',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:topic:list' AND `menu_type` = 'C' LIMIT 1),
       '2', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:topic:add', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:topic:add');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '主题修改',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:topic:list' AND `menu_type` = 'C' LIMIT 1),
       '3', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:topic:edit', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:topic:edit');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '主题删除',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:topic:list' AND `menu_type` = 'C' LIMIT 1),
       '4', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:topic:remove', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:topic:remove');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '主题重试',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:topic:list' AND `menu_type` = 'C' LIMIT 1),
       '5', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:topic:retry', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:topic:retry');

INSERT INTO `sys_role_menu` (`role_id`, `menu_id`)
SELECT 1, m.menu_id
FROM `sys_menu` m
WHERE m.perms IN (
    'rag:topic:list',
    'rag:topic:query',
    'rag:topic:add',
    'rag:topic:edit',
    'rag:topic:remove',
    'rag:topic:retry'
)
AND NOT EXISTS (
    SELECT 1 FROM `sys_role_menu` rm WHERE rm.role_id = 1 AND rm.menu_id = m.menu_id
);

-- 抽词改为异步后补充状态。已建表的环境补列，可重复执行。
SET @topic_status_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_retrieve_topic' AND COLUMN_NAME = 'status') = 0,
        'ALTER TABLE `knowledge_retrieve_topic` ADD COLUMN `status` varchar(32) NOT NULL DEFAULT ''READY'' COMMENT ''GENERATING生成中 READY已完成 FAILED失败'' AFTER `keyword_count`',
        'SELECT 1'
    )
);
PREPARE topic_status_stmt FROM @topic_status_sql;
EXECUTE topic_status_stmt;
DEALLOCATE PREPARE topic_status_stmt;

SET @topic_error_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_retrieve_topic' AND COLUMN_NAME = 'error_message') = 0,
        'ALTER TABLE `knowledge_retrieve_topic` ADD COLUMN `error_message` varchar(2000) DEFAULT NULL COMMENT ''抽词失败原因'' AFTER `status`',
        'SELECT 1'
    )
);
PREPARE topic_error_stmt FROM @topic_error_sql;
EXECUTE topic_error_stmt;
DEALLOCATE PREPARE topic_error_stmt;

SET @topic_keep_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_retrieve_topic' AND COLUMN_NAME = 'keep_keywords') = 0,
        'ALTER TABLE `knowledge_retrieve_topic` ADD COLUMN `keep_keywords` char(1) NOT NULL DEFAULT ''0'' COMMENT ''本次抽词是否保留旧关键词（0否 1是）'' AFTER `status`',
        'SELECT 1'
    )
);
PREPARE topic_keep_stmt FROM @topic_keep_sql;
EXECUTE topic_keep_stmt;
DEALLOCATE PREPARE topic_keep_stmt;

SET @topic_desc_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_retrieve_topic' AND COLUMN_NAME = 'description') = 0,
        'ALTER TABLE `knowledge_retrieve_topic` ADD COLUMN `description` varchar(1000) DEFAULT NULL COMMENT ''主题描述，最多1000字'' AFTER `topic_name`',
        'SELECT 1'
    )
);
PREPARE topic_desc_stmt FROM @topic_desc_sql;
EXECUTE topic_desc_stmt;
DEALLOCATE PREPARE topic_desc_stmt;

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '主题抽词兜底', 'default', 'default',
    'knowledge_content.tasks.topic_keyword_scheduler.topic_keyword_fallback_job',
    '', '', '0 */2 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每2分钟：GENERATING 超过3分钟且无人执行则重投抽词消息'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.topic_keyword_scheduler.topic_keyword_fallback_job'
);
