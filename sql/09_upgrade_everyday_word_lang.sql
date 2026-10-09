-- =============================================================================
-- 09_upgrade_everyday_word_lang.sql
-- 语种和词类分开。英文不再算词类。词类取值由程序回填。
-- 可重复执行
-- =============================================================================

SET @everyday_lang_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_everyday_word' AND COLUMN_NAME = 'lang') = 0,
        'ALTER TABLE `knowledge_everyday_word` ADD COLUMN `lang` varchar(8) NOT NULL DEFAULT ''zh'' COMMENT ''语种 zh中文 en英文'' AFTER `word`',
        'SELECT 1'
    )
);
PREPARE everyday_lang_stmt FROM @everyday_lang_sql;
EXECUTE everyday_lang_stmt;
DEALLOCATE PREPARE everyday_lang_stmt;

SET @everyday_lang_idx_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.STATISTICS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_everyday_word' AND INDEX_NAME = 'idx_everyday_lang') = 0,
        'ALTER TABLE `knowledge_everyday_word` ADD KEY `idx_everyday_lang` (`lang`)',
        'SELECT 1'
    )
);
PREPARE everyday_lang_idx_stmt FROM @everyday_lang_idx_sql;
EXECUTE everyday_lang_idx_stmt;
DEALLOCATE PREPARE everyday_lang_idx_stmt;

ALTER TABLE `knowledge_everyday_word`
    MODIFY COLUMN `word_class` varchar(16) NOT NULL DEFAULT 'other' COMMENT '词类 noun名词 verb动词 adj形容词 function虚词 other其他';

UPDATE `sys_menu`
SET `remark` = '全库一份日常词，可按语种和词类查看并剔除',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `path` = 'everyday' AND `component` = 'knowledge/everyday/index' AND `menu_type` = 'C';
