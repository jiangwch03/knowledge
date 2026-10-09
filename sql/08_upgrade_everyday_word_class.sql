-- =============================================================================
-- 08_upgrade_everyday_word_class.sql
-- 日常词不挂主题：表改名，补词类，菜单从主题权限下移开
-- 已执行过 07 第一版的环境跑这份。可重复执行
-- =============================================================================

SET @rename_everyday_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.TABLES
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_topic_everyday_word') > 0
        AND (SELECT COUNT(*) FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_everyday_word') = 0,
        'RENAME TABLE `knowledge_topic_everyday_word` TO `knowledge_everyday_word`',
        'SELECT 1'
    )
);
PREPARE rename_everyday_stmt FROM @rename_everyday_sql;
EXECUTE rename_everyday_stmt;
DEALLOCATE PREPARE rename_everyday_stmt;

SET @everyday_class_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_everyday_word' AND COLUMN_NAME = 'word_class') = 0,
        'ALTER TABLE `knowledge_everyday_word` ADD COLUMN `word_class` varchar(16) NOT NULL DEFAULT ''other'' COMMENT ''词类 noun名词 verb动词 adj形容词 function虚词 other其他'' AFTER `word`',
        'SELECT 1'
    )
);
PREPARE everyday_class_stmt FROM @everyday_class_sql;
EXECUTE everyday_class_stmt;
DEALLOCATE PREPARE everyday_class_stmt;

UPDATE `sys_menu`
SET `component` = 'knowledge/everyday/index',
    `perms` = 'rag:everyday:list',
    `remark` = '全库一份日常词，可按词类查看并剔除',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `perms` = 'rag:topic:everyday:list' AND `menu_type` = 'C';

UPDATE `sys_menu`
SET `perms` = 'rag:everyday:remove',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `perms` = 'rag:topic:everyday:remove';
