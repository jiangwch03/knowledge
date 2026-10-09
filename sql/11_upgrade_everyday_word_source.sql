-- =============================================================================
-- 11_upgrade_everyday_word_source.sql
-- 日常词标注来源。取值由程序回填：中文词频表、常用英语、手工录入。
-- 可重复执行
-- =============================================================================

SET @everyday_source_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_everyday_word' AND COLUMN_NAME = 'source') = 0,
        'ALTER TABLE `knowledge_everyday_word` ADD COLUMN `source` varchar(16) NOT NULL DEFAULT ''manual'' COMMENT ''来源 zh_idf中文词频表 en_common常用英语 manual手工录入'' AFTER `word_class`',
        'SELECT 1'
    )
);
PREPARE everyday_source_stmt FROM @everyday_source_sql;
EXECUTE everyday_source_stmt;
DEALLOCATE PREPARE everyday_source_stmt;

SET @everyday_source_idx_sql = (
    SELECT IF(
        (SELECT COUNT(*) FROM information_schema.STATISTICS
         WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'knowledge_everyday_word' AND INDEX_NAME = 'idx_everyday_source') = 0,
        'ALTER TABLE `knowledge_everyday_word` ADD KEY `idx_everyday_source` (`source`)',
        'SELECT 1'
    )
);
PREPARE everyday_source_idx_stmt FROM @everyday_source_idx_sql;
EXECUTE everyday_source_idx_stmt;
DEALLOCATE PREPARE everyday_source_idx_stmt;
