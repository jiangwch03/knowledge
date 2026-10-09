-- =============================================================================
-- 05_upgrade_knowledge_publish_eval.sql
-- 知识库发布评测：下线 Embedding 自动发布；新增 knowledge_eval_* 表与菜单权限
-- 依赖：02 已注册 embedding_auto_publish_job；正式发布改由 admin 测评任务编排
-- 可重复执行
-- =============================================================================

DELETE FROM `sys_job`
WHERE `invoke_target` = 'knowledge_content.tasks.embedding_task_scheduler.embedding_auto_publish_job';

-- ---------- 测评集 ----------
CREATE TABLE IF NOT EXISTS `knowledge_eval_dataset` (
    `dataset_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name` varchar(128) NOT NULL COMMENT '名称',
    `doc_id` bigint NOT NULL COMMENT '绑定文档',
    `description` varchar(500) DEFAULT NULL COMMENT '描述',
    `status` varchar(32) NOT NULL DEFAULT 'INIT' COMMENT 'INIT初始化 MATERIAL_DONE圈资料完成 SIMPLE_DONE简单题完成 MULTI_DONE多跳题完成 READY可测评，失败为对应_FAILED',
    `item_count` int DEFAULT 0 COMMENT '当前保留的题目数，出题完成前为0',
    `question_count` int NOT NULL DEFAULT 1 COMMENT '创建时要求生成的题目数',
    `material_plan` mediumtext COMMENT '圈资料结果 JSON，含抽中的材料和下载对象名',
    `user_id` bigint DEFAULT NULL COMMENT '归属用户',
    `dept_id` bigint DEFAULT NULL COMMENT '归属部门',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0存在 2删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`dataset_id`),
    KEY `idx_doc_id` (`doc_id`),
    KEY `idx_status` (`status`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库测评集';

CREATE TABLE IF NOT EXISTS `knowledge_eval_dataset_item` (
    `item_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `dataset_id` bigint NOT NULL COMMENT '测评集ID',
    `question` text NOT NULL COMMENT '问题',
    `ground_truth` text COMMENT '标准答案',
    `reference_excerpts` mediumtext COMMENT '出题依据的原文摘录 JSON 数组',
    `used_chunk_ids` text COMMENT '出题时用到的分段 chunk_id JSON 数组，用来回溯题目来自哪些分段',
    `keypoints` text COMMENT '合成这道题用到的要点 JSON 数组，没有则为空',
    `difficulty` varchar(64) DEFAULT NULL COMMENT '出题策略名，来自 RAGAS synthesizer_name，不是简单/中等/困难',
    `sort_order` int DEFAULT 0 COMMENT '排序',
    `enabled` tinyint DEFAULT 1 COMMENT '1跑测评时计入这道题，0人工排除不参与测评，题目仍保留',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志',
    PRIMARY KEY (`item_id`),
    KEY `idx_dataset_id` (`dataset_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库测评集题目';

CREATE TABLE IF NOT EXISTS `knowledge_eval_task` (
    `eval_task_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `name` varchar(128) DEFAULT NULL COMMENT '任务名称',
    `embedding_task_id` bigint NOT NULL COMMENT '要评测的向量化任务，须为待发布的 canary',
    `doc_id` bigint NOT NULL COMMENT '文档ID，与测评集、向量化任务是同一篇文档',
    `dataset_id` bigint NOT NULL COMMENT '当前绑定的测评集，发布前可更换',
    `status` varchar(32) NOT NULL DEFAULT 'OPEN' COMMENT 'OPEN进行中，可换测评集、再跑、发布；ARCHIVED已发布归档，不能再跑',
    `publish_time` datetime DEFAULT NULL COMMENT '向量从待发布版本发布到正式环境的时间',
    `user_id` bigint DEFAULT NULL COMMENT '归属用户',
    `dept_id` bigint DEFAULT NULL COMMENT '归属部门',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`eval_task_id`),
    KEY `idx_embedding_task_id` (`embedding_task_id`),
    KEY `idx_dataset_id` (`dataset_id`),
    KEY `idx_status` (`status`),
    KEY `idx_doc_id` (`doc_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库测评任务';

CREATE TABLE IF NOT EXISTS `knowledge_eval_run` (
    `run_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `eval_task_id` bigint NOT NULL COMMENT '所属测评任务，一个任务可多次执行',
    `dataset_id` bigint NOT NULL COMMENT '这次执行使用的测评集',
    `embedding_task_id` bigint NOT NULL COMMENT '这次考的向量化任务',
    `release_tag` varchar(32) DEFAULT 'canary' COMMENT '考的是待发布版本 canary，不是已发布的正式版',
    `status` varchar(32) NOT NULL DEFAULT 'PENDING' COMMENT 'PENDING待执行 RUNNING执行中 SUCCESS成功 FAILED失败',
    `dataset_snapshot` mediumtext COMMENT '开跑时计入测评的题目快照 JSON，之后改题不影响这次记录',
    `summary_metrics` text COMMENT '本次执行四项均分 JSON：context_recall上下文召回、context_precision上下文精确率、faithfulness回答是否忠于原文、answer_relevancy回答是否贴题；按有分的题目取平均，0到1',
    `report_text` mediumtext COMMENT '评分异常说明，正常完成为空',
    `embedding_model_code` varchar(128) DEFAULT NULL COMMENT '这次作答使用的向量模型',
    `llm_version` varchar(128) DEFAULT NULL COMMENT '这次作答使用的问答模型',
    `judge_model_code` varchar(128) DEFAULT NULL COMMENT '给检索结果和回答打分的裁判模型',
    `error_message` varchar(2000) DEFAULT NULL COMMENT '这次执行失败的原因',
    `started_at` datetime DEFAULT NULL COMMENT '开始时间',
    `finished_at` datetime DEFAULT NULL COMMENT '结束时间',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志',
    PRIMARY KEY (`run_id`),
    KEY `idx_eval_task_id` (`eval_task_id`),
    KEY `idx_status` (`status`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='一次测评执行。同一任务可多次执行，每次一条';

CREATE TABLE IF NOT EXISTS `knowledge_eval_run_item` (
    `run_item_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键',
    `run_id` bigint NOT NULL COMMENT '所属的一次测评执行',
    `dataset_item_id` bigint DEFAULT NULL COMMENT '对应测评集里的哪一道题',
    `question` text COMMENT '开跑时的问题，之后改题不影响这次记录',
    `ground_truth` text COMMENT '开跑时的标准答案',
    `reference_excerpts` mediumtext COMMENT '开跑时的原文摘录 JSON 数组',
    `contexts` mediumtext COMMENT '这次检索召回的原文片段 JSON 数组',
    `answer` mediumtext COMMENT '知识库针对这道题给出的回答',
    `metrics` text COMMENT '这道题的四项分数 JSON：context_recall、context_precision、faithfulness、answer_relevancy，0到1',
    `sort_order` int DEFAULT 0 COMMENT '这道题在本次执行中的顺序',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志',
    PRIMARY KEY (`run_item_id`),
    KEY `idx_run_id` (`run_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='一次测评执行中的逐题结果：问题、检索、回答和这道题的分数';

-- ---------- 菜单 / 权限（挂在 knowledge 目录下） ----------
INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '测评集', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0' LIMIT 1),
       '6', 'eval-dataset', 'knowledge/eval/dataset/index', '', '', 1, 0, 'C', '0', '0',
       'rag:eval:dataset:list', 'form', 'admin', NOW(), 'admin', NOW(), '知识库测评集'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:list' AND `menu_type` = 'C');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '测评任务', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0' LIMIT 1),
       '7', 'eval-task', 'knowledge/eval/task/index', '', '', 1, 0, 'C', '0', '0',
       'rag:eval:task:list', 'job', 'admin', NOW(), 'admin', NOW(), '知识库测评任务'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:task:list' AND `menu_type` = 'C');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '测评集查询', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:list' AND `menu_type` = 'C' LIMIT 1),
       '1', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:dataset:query', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:query');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '测评集生成', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:list' AND `menu_type` = 'C' LIMIT 1),
       '2', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:dataset:create', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:create');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '测评集改题', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:list' AND `menu_type` = 'C' LIMIT 1),
       '3', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:dataset:edit', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:dataset:edit');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '测评任务查询', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:task:list' AND `menu_type` = 'C' LIMIT 1),
       '1', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:task:query', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:task:query');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '测评任务创建', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:task:list' AND `menu_type` = 'C' LIMIT 1),
       '2', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:task:create', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:task:create');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '跑测评', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:task:list' AND `menu_type` = 'C' LIMIT 1),
       '3', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:task:run', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:task:run');

INSERT INTO `sys_menu` (`menu_name`,`parent_id`,`order_num`,`path`,`component`,`query`,`route_name`,`is_frame`,`is_cache`,`menu_type`,`visible`,`status`,`perms`,`icon`,`create_by`,`create_time`,`update_by`,`update_time`,`remark`)
SELECT '发布', (SELECT `menu_id` FROM `sys_menu` WHERE `perms` = 'rag:eval:task:list' AND `menu_type` = 'C' LIMIT 1),
       '4', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:eval:task:publish', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:eval:task:publish');

-- 已执行过旧版建表时补列（可重复执行）
SET @db := DATABASE();
SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE `knowledge_eval_dataset` ADD COLUMN `question_count` int NOT NULL DEFAULT 1 COMMENT ''请求生成的题目数量'' AFTER `item_count`',
        'SELECT 1'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'knowledge_eval_dataset' AND COLUMN_NAME = 'question_count'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'ALTER TABLE `knowledge_eval_dataset` ADD COLUMN `material_plan` mediumtext COMMENT ''圈资料结果 JSON，含抽中的材料和下载对象名'' AFTER `question_count`',
        'SELECT 1'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'knowledge_eval_dataset' AND COLUMN_NAME = 'material_plan'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE `knowledge_eval_dataset`
    MODIFY COLUMN `status` varchar(32) NOT NULL DEFAULT 'INIT'
        COMMENT 'INIT初始化 MATERIAL_DONE圈资料完成 SIMPLE_DONE简单题完成 MULTI_DONE多跳题完成 READY可测评，失败为对应_FAILED';

SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'SELECT 1',
        'UPDATE `knowledge_eval_dataset` SET `status` = CASE WHEN `stage` IN (''MATERIAL_DONE'', ''SIMPLE_DONE'', ''MULTI_DONE'', ''MATERIAL_FAILED'', ''SIMPLE_FAILED'', ''MULTI_FAILED'', ''CUSTOM_FAILED'') THEN `stage` WHEN `stage` = ''CUSTOM_DONE'' THEN ''READY'' WHEN `status` = ''FAILED'' THEN ''CUSTOM_FAILED'' ELSE ''INIT'' END WHERE `status` IN (''DRAFT'', ''GENERATING'', ''FAILED'')'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'knowledge_eval_dataset' AND COLUMN_NAME = 'stage'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @sql := (
    SELECT IF(
        COUNT(*) = 0,
        'SELECT 1',
        'ALTER TABLE `knowledge_eval_dataset` DROP COLUMN `stage`'
    )
    FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = @db AND TABLE_NAME = 'knowledge_eval_dataset' AND COLUMN_NAME = 'stage'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

ALTER TABLE `knowledge_eval_dataset_item`
    MODIFY COLUMN `difficulty` varchar(64) DEFAULT NULL COMMENT '出题策略名，来自 RAGAS synthesizer_name，不是简单/中等/困难';

-- 整份题目快照和逐题检索/回答会超过 TEXT 的 64KB
ALTER TABLE `knowledge_eval_run`
    MODIFY COLUMN `dataset_snapshot` mediumtext COMMENT '开跑时计入测评的题目快照 JSON，之后改题不影响这次记录',
    MODIFY COLUMN `report_text` mediumtext COMMENT '评分异常说明，正常完成为空';

ALTER TABLE `knowledge_eval_run_item`
    MODIFY COLUMN `reference_excerpts` mediumtext COMMENT '开跑时的原文摘录 JSON 数组',
    MODIFY COLUMN `contexts` mediumtext COMMENT '这次检索召回的原文片段 JSON 数组',
    MODIFY COLUMN `answer` mediumtext COMMENT '知识库针对这道题给出的回答';

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    '测评集生成兜底', 'default', 'default',
    'knowledge_admin.tasks.eval_dataset_scheduler.eval_dataset_fallback_job',
    '', '', '0 * * * * ?', '3', '1', '0', 'knowledge-admin',
    'admin', NOW(), 'admin', NOW(), '每分钟重投递超时仍在出题的测评集，并重试出题失败的测评集'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_admin.tasks.eval_dataset_scheduler.eval_dataset_fallback_job'
);

UPDATE `sys_job`
SET `cron_expression` = '0 * * * * ?',
    `remark` = '每分钟重投递超时仍在出题的测评集，并重试出题失败的测评集',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `invoke_target` = 'knowledge_admin.tasks.eval_dataset_scheduler.eval_dataset_fallback_job';

-- 测评集出题与指标评分的对话模型。qwen-plus 是文本对话模型；
-- 向量继续用已有的 document_embedding（text-embedding-v4），不另配。
INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`,
    `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    '测评集出题与评分',
    'eval_dataset',
    CAST((SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'qwen-plus' LIMIT 1) AS CHAR),
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'eval_dataset' AND `del_flag` = '0'
)
AND EXISTS (SELECT 1 FROM `ai_models` WHERE `model_code` = 'qwen-plus');
