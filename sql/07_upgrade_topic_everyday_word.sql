-- =============================================================================
-- 07_upgrade_topic_everyday_word.sql
-- 主题抽词日常词：入库、菜单、每天 03:00 把未剔除的词装进 Redis
-- 可重复执行
-- =============================================================================

CREATE TABLE IF NOT EXISTS `knowledge_everyday_word` (
    `word_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `word` varchar(64) NOT NULL COMMENT '日常词',
    `lang` varchar(8) NOT NULL DEFAULT 'zh' COMMENT '语种 zh中文 en英文',
    `word_class` varchar(16) NOT NULL DEFAULT 'other' COMMENT '词类 noun名词 verb动词 adj形容词 function虚词 other其他',
    `source` varchar(16) NOT NULL DEFAULT 'manual' COMMENT '来源 zh_idf中文词频表 en_common常用英语 manual手工录入',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0在用 2已剔除）',
    PRIMARY KEY (`word_id`),
    UNIQUE KEY `uk_everyday_word` (`word`),
    KEY `idx_everyday_del_flag` (`del_flag`),
    KEY `idx_everyday_lang` (`lang`),
    KEY `idx_everyday_class` (`word_class`),
    KEY `idx_everyday_source` (`source`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='抽词日常词，全库一份，不挂主题';

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '日常词',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0' LIMIT 1),
       '9', 'everyday', 'knowledge/everyday/index', '', '',
       1, 0, 'C', '1', '0', 'rag:everyday:list', 'edit',
       'admin', NOW(), 'admin', NOW(), '挂在主题管理页里，侧栏不单列'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:everyday:list' AND `menu_type` = 'C'
);

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '日常词剔除',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:everyday:list' AND `menu_type` = 'C' LIMIT 1),
       '1', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:everyday:remove', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:everyday:remove');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '日常词新增',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:everyday:list' AND `menu_type` = 'C' LIMIT 1),
       '2', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:everyday:add', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:everyday:add');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '日常词初始化',
       (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:everyday:list' AND `menu_type` = 'C' LIMIT 1),
       '3', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:everyday:init', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:everyday:init');

INSERT INTO `sys_role_menu` (`role_id`, `menu_id`)
SELECT 1, m.menu_id
FROM `sys_menu` m
WHERE m.perms IN ('rag:everyday:list', 'rag:everyday:add', 'rag:everyday:init', 'rag:everyday:remove')
AND NOT EXISTS (
    SELECT 1 FROM `sys_role_menu` rm WHERE rm.role_id = 1 AND rm.menu_id = m.menu_id
);

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '日常词缓存刷新', 'default', 'default',
    'knowledge_content.tasks.topic_everyday_scheduler.topic_everyday_cache_job',
    '', '', '0 0 3 * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每天 03:00 把未剔除的日常词从库装进 Redis'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.topic_everyday_scheduler.topic_everyday_cache_job'
);
