-- =============================================================================
-- 12_upgrade_everyday_word_init.sql
-- 日常词页面增加「初始化」按钮权限
-- 可重复执行
-- =============================================================================

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
WHERE m.perms = 'rag:everyday:init'
AND NOT EXISTS (
    SELECT 1 FROM `sys_role_menu` rm WHERE rm.role_id = 1 AND rm.menu_id = m.menu_id
);
