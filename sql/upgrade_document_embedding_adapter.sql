-- =============================================================================
-- 独立升级：文档向量化业务适配（可单独执行，可重复执行）
--
-- 作用：
--   1. knowledge_ai_model_function_adapter 增加 dimensions
--   2. 若 ai_models 误加了 dimensions，则删除（维度以业务适配为准）
--   3. 种子 text-embedding-v4 + document_embedding（默认维度 1024）
--
-- 执行示例：
--   mysql -h <host> -P <port> -u <user> -p --default-character-set=utf8mb4 <database> < sql/upgrade_document_embedding_adapter.sql
-- =============================================================================

SET NAMES utf8mb4;

-- 1) 业务适配增加 dimensions
SET @adapter_dimensions_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'knowledge_ai_model_function_adapter'
      AND COLUMN_NAME = 'dimensions'
);
SET @adapter_dimensions_sql := IF(
    @adapter_dimensions_exists = 0,
    'ALTER TABLE `knowledge_ai_model_function_adapter` ADD COLUMN `dimensions` int DEFAULT NULL COMMENT ''向量维度（Embedding 业务适配必填，如 document_embedding）'' AFTER `model_id`',
    'SELECT ''knowledge_ai_model_function_adapter.dimensions already exists'''
);
PREPARE stmt FROM @adapter_dimensions_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2) 清理误加在 ai_models 上的 dimensions
SET @ai_models_dimensions_exists := (
    SELECT COUNT(*) FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'ai_models'
      AND COLUMN_NAME = 'dimensions'
);
SET @ai_models_dimensions_drop_sql := IF(
    @ai_models_dimensions_exists > 0,
    'ALTER TABLE `ai_models` DROP COLUMN `dimensions`',
    'SELECT ''ai_models.dimensions not present'''
);
PREPARE stmt FROM @ai_models_dimensions_drop_sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 3) 种子 Embedding 模型：通义千问 text-embedding-v4
INSERT INTO `ai_models` (
    `model_code`, `model_name`, `provider`, `model_sort`, `api_key`, `base_url`,
    `model_type`, `max_tokens`, `temperature`, `support_reasoning`, `support_images`,
    `status`, `user_id`, `dept_id`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'text-embedding-v4', '通义千问 Embedding V4', 'openai', 4,
    'sk-你自己的key',
    'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'embedding', NULL, NULL, 'N', 'N',
    '0', 1, 1, 'admin', NOW(), 'admin', NOW(),
    '通义千问 text-embedding-v4，维度在业务适配 document_embedding 配置'
WHERE NOT EXISTS (SELECT 1 FROM `ai_models` WHERE `model_code` = 'text-embedding-v4');

-- 4) 种子业务适配 document_embedding（默认 1024 维）
INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`, `dimensions`,
    `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    '文档向量化',
    'document_embedding',
    CAST((SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'text-embedding-v4') AS CHAR),
    1024,
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'document_embedding' AND `del_flag` = '0'
);
