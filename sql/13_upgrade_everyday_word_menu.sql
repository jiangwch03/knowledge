-- =============================================================================
-- 13_upgrade_everyday_word_menu.sql
-- 日常词不单独占侧栏，改在主题管理页里打开。权限保留。
-- 可重复执行
-- =============================================================================

UPDATE `sys_menu`
SET `visible` = '1',
    `remark` = '挂在主题管理页里，侧栏不单列',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `perms` = 'rag:everyday:list' AND `menu_type` = 'C';
