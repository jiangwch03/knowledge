-- ----------------------------------------------------------------------------
-- 网页爬取 Agent 全量升级脚本（合并版）
--
-- 合并自：
--   upgrade_web_crawler_agent.sql
--   upgrade_agent_chat.sql
--   upgrade_crawl_proxy_pool_dict.sql
--   upgrade_web_crawler_task_version.sql
--
-- 适用：新环境全量初始化；已跑过旧版脚本的库可重复执行（幂等）
-- 创建时间: 2026-07-09
-- ----------------------------------------------------------------------------

-- ============================================================================
-- 1、Agent 会话/消息表（最终表名 knowledge_agent_*，含 agent_type）
-- ============================================================================

-- 1.1 旧表名迁移（web_crawler_* → agent_*）
SET @session_old_exists = (
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'knowledge_web_crawler_session'
);
SET @session_new_exists = (
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'knowledge_agent_session'
);
SET @sql_rename_session = IF(
    @session_old_exists > 0 AND @session_new_exists = 0,
    'RENAME TABLE `knowledge_web_crawler_session` TO `knowledge_agent_session`',
    'SELECT 1'
);
PREPARE stmt FROM @sql_rename_session;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @message_old_exists = (
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'knowledge_web_crawler_message'
);
SET @message_new_exists = (
    SELECT COUNT(*) FROM information_schema.tables
    WHERE table_schema = DATABASE() AND table_name = 'knowledge_agent_message'
);
SET @sql_rename_message = IF(
    @message_old_exists > 0 AND @message_new_exists = 0,
    'RENAME TABLE `knowledge_web_crawler_message` TO `knowledge_agent_message`',
    'SELECT 1'
);
PREPARE stmt FROM @sql_rename_message;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 1.2 新环境建表
CREATE TABLE IF NOT EXISTS `knowledge_agent_session` (
    `session_id` bigint NOT NULL AUTO_INCREMENT COMMENT '会话ID',
    `agent_type` varchar(50) NOT NULL DEFAULT 'web_crawler' COMMENT 'Agent类型，如 web_crawler',
    `session_title` varchar(255) DEFAULT NULL COMMENT '会话标题',
    `status` varchar(20) DEFAULT 'ACTIVE' COMMENT '会话状态 ACTIVE/CLOSED',
    `model_id` bigint DEFAULT NULL COMMENT '选择的模型ID',
    `user_id` bigint NOT NULL COMMENT '用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`session_id`),
    KEY `idx_user_agent` (`user_id`, `agent_type`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 会话表';

CREATE TABLE IF NOT EXISTS `knowledge_agent_message` (
    `message_id` bigint NOT NULL AUTO_INCREMENT COMMENT '消息ID',
    `session_id` bigint NOT NULL COMMENT '关联会话ID',
    `role` varchar(20) NOT NULL COMMENT '消息角色 human/ai/system/tool（与LangChain对齐）',
    `content` text COMMENT '消息内容',
    `tool_call_id` varchar(100) DEFAULT NULL COMMENT '工具调用ID（role=tool时使用）',
    `tool_name` varchar(100) DEFAULT NULL COMMENT '工具名称（role=tool时使用）',
    `user_id` bigint NOT NULL COMMENT '用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`message_id`),
    KEY `idx_session_id` (`session_id`),
    KEY `idx_role` (`role`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Agent 消息表';

-- 1.3 已有 agent_session 补 agent_type 列与索引
SET @agent_type_col_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'knowledge_agent_session'
      AND column_name = 'agent_type'
);
SET @sql_add_agent_type = IF(
    @agent_type_col_exists = 0,
    'ALTER TABLE `knowledge_agent_session` ADD COLUMN `agent_type` varchar(50) NOT NULL DEFAULT ''web_crawler'' COMMENT ''Agent类型，如 web_crawler'' AFTER `session_id`',
    'SELECT 1'
);
PREPARE stmt FROM @sql_add_agent_type;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

UPDATE `knowledge_agent_session` SET `agent_type` = 'web_crawler' WHERE `agent_type` IS NULL OR `agent_type` = '';

SET @idx_user_agent_exists = (
    SELECT COUNT(*) FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'knowledge_agent_session'
      AND index_name = 'idx_user_agent'
);
SET @sql_add_idx_user_agent = IF(
    @idx_user_agent_exists = 0,
    'ALTER TABLE `knowledge_agent_session` ADD KEY `idx_user_agent` (`user_id`, `agent_type`)',
    'SELECT 1'
);
PREPARE stmt FROM @sql_add_idx_user_agent;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================================
-- 2、爬取任务表（含 doc_version）
-- ============================================================================
CREATE TABLE IF NOT EXISTS `knowledge_web_crawler_task` (
    `task_id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务ID',
    `doc_version` varchar(20) DEFAULT NULL COMMENT '文档版本号（创建时预分配，落库时沿用）',
    `target_url` varchar(1000) NOT NULL COMMENT '目标URL',
    `crawl_config` text COMMENT 'crawl4ai 爬取策略配置JSON',
    `status` varchar(20) DEFAULT 'PENDING' COMMENT '任务状态 PENDING/RUNNING/COMPLETED/CONVERTED/CONVERT_FAILED/FAILED/USER_DECISION/PAUSED',
    `progress` int DEFAULT '0' COMMENT '进度百分比 0-100',
    `current_step` varchar(255) DEFAULT NULL COMMENT '当前执行步骤描述',
    `success_count` int DEFAULT '0' COMMENT '成功页面数',
    `failed_count` int DEFAULT '0' COMMENT '失败页面数',
    `total_count` int DEFAULT '0' COMMENT '总页面数',
    `error_code` varchar(50) DEFAULT NULL COMMENT '错误码',
    `error_message` text COMMENT '错误信息',
    `retry_count` int DEFAULT '0' COMMENT '已重试次数（达到 max_retry_count 后升级为用户人工决策）',
    `max_retry_count` int DEFAULT '2' COMMENT '规则自动重试上限；LLM 人工重试时 += crawl4ai_rule_retry_limit',
    `started_time` datetime DEFAULT NULL COMMENT '任务开始时间',
    `completed_time` datetime DEFAULT NULL COMMENT '任务完成时间',
    `user_id` bigint NOT NULL COMMENT '用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`task_id`),
    KEY `idx_status` (`status`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_target_url` (`target_url`(255)),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爬取任务表';

SET @doc_version_col_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'knowledge_web_crawler_task'
      AND column_name = 'doc_version'
);
SET @sql_add_doc_version = IF(
    @doc_version_col_exists = 0,
    'ALTER TABLE `knowledge_web_crawler_task` ADD COLUMN `doc_version` varchar(20) DEFAULT NULL COMMENT ''文档版本号（创建时预分配，落库时沿用）'' AFTER `task_id`',
    'SELECT 1'
);
PREPARE stmt FROM @sql_add_doc_version;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @max_retry_count_col_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'knowledge_web_crawler_task'
      AND column_name = 'max_retry_count'
);
SET @sql_add_max_retry_count = IF(
    @max_retry_count_col_exists = 0,
    'ALTER TABLE `knowledge_web_crawler_task` ADD COLUMN `max_retry_count` int DEFAULT ''2'' COMMENT ''规则自动重试上限；LLM 人工重试时 += crawl4ai_rule_retry_limit'' AFTER `retry_count`',
    'SELECT 1'
);
PREPARE stmt FROM @sql_add_max_retry_count;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- ============================================================================
-- 3、爬取任务 URL 记录表
-- ============================================================================
CREATE TABLE IF NOT EXISTS `knowledge_web_crawler_task_url_record` (
    `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
    `task_id` bigint NOT NULL COMMENT '关联任务ID',
    `url` varchar(1000) NOT NULL COMMENT '原始页面URL',
    `status` varchar(20) DEFAULT 'PENDING' COMMENT '记录状态 PENDING/SUCCESS/FAILED',
    `doc_key` varchar(500) DEFAULT NULL COMMENT '页面markdown的MinIO对象键',
    `title` varchar(255) DEFAULT NULL COMMENT '页面标题',
    `status_code` int DEFAULT NULL COMMENT 'HTTP状态码',
    `error_code` varchar(50) DEFAULT NULL COMMENT '错误码',
    `error_message` text COMMENT '错误详情',
    `retry_count` int DEFAULT '0' COMMENT '重试次数',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    PRIMARY KEY (`id`),
    KEY `idx_task_id` (`task_id`),
    KEY `idx_status` (`status`),
    KEY `idx_url` (`url`(255))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='爬取任务URL记录表';

-- ============================================================================
-- 4、清理废弃表
-- ============================================================================
DROP TABLE IF EXISTS `knowledge_web_crawler_message_task`;

-- ============================================================================
-- 5、爬虫代理池字典
-- ============================================================================
INSERT INTO `sys_dict_type` (
    `dict_name`, `dict_type`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
    '爬虫代理池',
    'crawl_proxy_pool',
    '0',
    'admin',
    NOW(),
    'admin',
    NOW(),
    '网页爬取 Agent 可用代理 IP 池；节点存于 sys_dict_data，dict_value 为 crawl4ai ProxyConfig JSON'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_type` WHERE `dict_type` = 'crawl_proxy_pool'
);

-- ============================================================================
-- 6、菜单与权限
-- ============================================================================
INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '网页爬虫', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0'), '2', 'crawler', 'knowledge/crawler/index', '', '', 1, 0, 'C', '0', '0', 'rag:crawler:list', 'web-crawl', 'admin', NOW(), 'admin', NOW(), '网页爬虫菜单'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'crawler' AND `component` = 'knowledge/crawler/index');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '会话管理', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'crawler' AND `component` = 'knowledge/crawler/index'), '1', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:crawler:session', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:crawler:session');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '爬取任务', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'crawler' AND `component` = 'knowledge/crawler/index'), '2', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:crawler:task', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:crawler:task');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '爬取文档', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'crawler' AND `component` = 'knowledge/crawler/index'), '3', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:crawler:document', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:crawler:document');

-- ============================================================================
-- 7、定时任务
-- ============================================================================
INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '爬取任务超时兜底', 'default', 'default',
    'knowledge_content.tasks.web_crawler_task_scheduler.crawl_task_timeout_job',
    '', '', '0 */5 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每5分钟扫描超时运行中的爬取任务并标记失败'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job` WHERE `invoke_target` = 'knowledge_content.tasks.web_crawler_task_scheduler.crawl_task_timeout_job');

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '爬取失败任务重试', 'default', 'default',
    'knowledge_content.tasks.web_crawler_task_scheduler.crawl_task_retry_job',
    '', '', '0 */3 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每3分钟扫描失败任务并尝试自动修复重试'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job` WHERE `invoke_target` = 'knowledge_content.tasks.web_crawler_task_scheduler.crawl_task_retry_job');

-- ============================================================================
-- 8、web_crawler_agent 模型功能适配
-- ============================================================================
INSERT INTO `ai_models` (
    `model_code`, `model_name`, `provider`, `model_sort`, `api_key`, `base_url`,
    `model_type`, `max_tokens`, `temperature`, `support_reasoning`, `support_images`,
    `status`, `user_id`, `dept_id`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'qwen-plus', 'Qwen-Plus', 'openai', 3,
    'sk-你自己的key',
    'https://dashscope.aliyuncs.com/compatible-mode/v1',
    'LLM', 8192, 0.7, 'N', 'N',
    '0', 1, 1, 'admin', NOW(), 'admin', NOW(), 'Qwen-Plus 网页爬取Agent模型'
WHERE NOT EXISTS (SELECT 1 FROM `ai_models` WHERE `model_code` = 'qwen-plus');

ALTER TABLE `knowledge_ai_model_function_adapter` DROP INDEX `idx_model_id`;
ALTER TABLE `knowledge_ai_model_function_adapter` MODIFY COLUMN `model_id` VARCHAR(500) NOT NULL COMMENT '关联模型ID，多个用|分隔';

INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`, `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    '网页爬取Agent',
    'web_crawler_agent',
    CAST((SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'qwen-plus') AS CHAR),
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'web_crawler_agent' AND `del_flag` = '0'
);
