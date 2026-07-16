-- ----------------------------------------------------------------------------
-- RAG 资料上传与 MinerU 解析能力升级脚本
-- 适用于已有数据库环境（新增 5 张表及相关初始化数据）
-- 创建时间: 2026-06-19
-- ----------------------------------------------------------------------------

-- ----------------------------
-- 1、文档主表
-- ----------------------------
DROP TABLE IF EXISTS `knowledge_document`;
CREATE TABLE `knowledge_document` (
    `doc_id` bigint NOT NULL AUTO_INCREMENT COMMENT '文档主键',
    `task_id` bigint DEFAULT NULL COMMENT '关联任务ID（source_type=0时为上传任务ID，source_type=1时为爬取任务ID）',
    `source_type` char(1) DEFAULT '0' COMMENT '来源类型（0-手动上传 1-网页爬取）',
    `doc_title` varchar(255) NOT NULL COMMENT '文档标题',
    `doc_desc` varchar(500) DEFAULT NULL COMMENT '文档描述',
    `doc_name` varchar(255) DEFAULT NULL COMMENT '文件名',
    `doc_type` varchar(50) DEFAULT NULL COMMENT '文档格式 PDF/DOC/DOCX/XLSX/MD',
    `source_url` text COMMENT '网页来源URL',
    `original_doc_key` varchar(500) DEFAULT NULL COMMENT '原始上传文件MinIO对象键',
    `doc_key` varchar(500) DEFAULT NULL COMMENT '最终Markdown MinIO对象键',
    `doc_version` varchar(20) DEFAULT '1.0' COMMENT '文档版本',
    `is_latest` char(1) DEFAULT '1' COMMENT '是否最新版本（0-否 1-是）',
    `version_remark` varchar(255) DEFAULT NULL COMMENT '版本说明',
    `status` varchar(20) DEFAULT 'CONVERTED' COMMENT '文档状态 CONVERTED/CHUNKED/VECTOR_STORED',
    `media_count` int DEFAULT '0' COMMENT '媒体文件数量',
    `user_id` bigint NOT NULL COMMENT '上传用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`doc_id`),
    UNIQUE KEY `uk_doc_title_version` (`doc_title`, `doc_version`),
    KEY `idx_doc_title` (`doc_title`),
    KEY `idx_source_type` (`source_type`),
    KEY `idx_is_latest` (`is_latest`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档主表';

-- ----------------------------
-- 2、文档上传任务表
-- ----------------------------
DROP TABLE IF EXISTS `knowledge_upload_document_parse_task`;
CREATE TABLE `knowledge_upload_document_parse_task` (
    `task_id` bigint NOT NULL AUTO_INCREMENT COMMENT '上传任务ID',
    `doc_title` varchar(255) NOT NULL COMMENT '文档标题',
    `doc_desc` varchar(500) DEFAULT NULL COMMENT '文档描述',
    `doc_name` varchar(255) DEFAULT NULL COMMENT '文件名',
    `doc_type` varchar(50) DEFAULT NULL COMMENT '文档格式',
    `doc_version` varchar(20) DEFAULT '1.0' COMMENT '文档版本号（上传时预占）',
    `is_latest` char(1) DEFAULT '1' COMMENT '是否最新版本（0-否 1-是）',
    `version_remark` varchar(255) DEFAULT NULL COMMENT '版本说明',
    `parse_required` char(1) DEFAULT '1' COMMENT '是否需要MinerU解析（0-否 1-是）',
    `original_doc_key` varchar(500) DEFAULT NULL COMMENT '原始文件MinIO对象键',
    `total_pages` int DEFAULT '0' COMMENT '总页数',
    `status` varchar(20) DEFAULT 'PENDING' COMMENT '状态 PENDING/LINK_FAILED/WAITING_UPLOAD/UPLOADING/PARSING/COMPLETED/USER_DECISION/CONVERTED/CONVERT_FAILED',
    `error_code` varchar(50) DEFAULT NULL COMMENT '错误码',
    `error_message` text COMMENT '错误信息',
    `user_id` bigint NOT NULL COMMENT '上传用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`task_id`),
    UNIQUE KEY `uk_doc_title_version` (`doc_title`, `doc_version`),
    KEY `idx_doc_title` (`doc_title`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档上传任务表';

-- ----------------------------
-- 3、MinerU解析任务表
-- ----------------------------
DROP TABLE IF EXISTS `knowledge_mineru_parse_task`;
CREATE TABLE `knowledge_mineru_parse_task` (
    `parse_task_id` bigint NOT NULL AUTO_INCREMENT COMMENT '解析任务ID',
    `task_id` bigint DEFAULT NULL COMMENT '关联上传任务ID',
    `parse_mode` varchar(20) DEFAULT 'document' COMMENT '解析模式 html/document',
    `enable_formula` char(1) DEFAULT '1' COMMENT '公式识别（0-否 1-是）',
    `enable_table` char(1) DEFAULT '1' COMMENT '表格识别（0-否 1-是）',
    `language` varchar(20) DEFAULT 'ch' COMMENT '文档语言',
    `is_ocr` char(1) DEFAULT '0' COMMENT 'OCR（0-否 1-是）',
    `status` varchar(20) DEFAULT 'PENDING' COMMENT '整体状态 PENDING/LINK_FAILED/WAITING_UPLOAD/UPLOADING/PARSING/COMPLETED/FAILED',
    `error_code` varchar(50) DEFAULT NULL COMMENT '错误码',
    `error_message` text COMMENT '错误信息',
    `batch_id` varchar(64) DEFAULT NULL COMMENT 'MinerU批次ID',
    `user_id` bigint NOT NULL COMMENT '上传用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`parse_task_id`),
    KEY `idx_task_id` (`task_id`),
    KEY `idx_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MinerU解析任务表';

-- ----------------------------
-- 4、MinerU解析批次/分段明细表
-- ----------------------------
DROP TABLE IF EXISTS `knowledge_mineru_parse_detail_task`;
CREATE TABLE `knowledge_mineru_parse_detail_task` (
    `detail_id` bigint NOT NULL AUTO_INCREMENT COMMENT '明细ID',
    `parse_task_id` bigint NOT NULL COMMENT '关联解析任务ID',
    `sequence_number` int NOT NULL COMMENT '分段序号，用于合并排序',
    `batch_id` varchar(64) DEFAULT NULL COMMENT 'MinerU批次ID（重试会变）',
    `data_id` varchar(64) DEFAULT NULL COMMENT 'MinerU数据ID（重试会变）',
    `page_ranges` varchar(50) DEFAULT NULL COMMENT '页码范围',
    `state` varchar(20) DEFAULT 'WAITING_UPLOAD' COMMENT '分段状态 WAITING_UPLOAD/UPLOAD_FAILED/PARSING/PARSED/PARSE_FAILED/RETRIED',
    `upload_url` varchar(500) DEFAULT NULL COMMENT '上传链接',
    `upload_expire_at` datetime DEFAULT NULL COMMENT '链接过期时间',
    `full_zip_url` varchar(500) DEFAULT NULL COMMENT '结果ZIP链接',
    `err_msg` text COMMENT '错误信息',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    PRIMARY KEY (`detail_id`),
    KEY `idx_parse_task_id` (`parse_task_id`),
    KEY `idx_sequence_number` (`sequence_number`),
    KEY `idx_batch_id` (`batch_id`),
    KEY `idx_state` (`state`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='MinerU解析批次/分段明细表';

-- ----------------------------
-- 5、模型功能适配表
-- ----------------------------
DROP TABLE IF EXISTS `knowledge_ai_model_function_adapter`;
CREATE TABLE `knowledge_ai_model_function_adapter` (
    `adapter_id` bigint NOT NULL AUTO_INCREMENT COMMENT '适配ID',
    `function_point` varchar(100) NOT NULL COMMENT '业务功能点',
    `param_id` varchar(64) NOT NULL COMMENT '参数ID，唯一标识业务功能',
    `model_id` varchar(500) NOT NULL COMMENT '关联模型ID，多个用|分隔',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    PRIMARY KEY (`adapter_id`),
    UNIQUE KEY `uk_param_id` (`param_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型功能适配表';

-- ----------------------------
-- 6、merio_language 字典初始化
-- ----------------------------
INSERT INTO `sys_dict_type` (`dict_name`, `dict_type`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT 'merio语言', 'merio_language', '0', 'admin', NOW(), 'admin', NOW(), 'merio OCR 识别语言配置'
WHERE NOT EXISTS (SELECT 1 FROM `sys_dict_type` WHERE `dict_type` = 'merio_language');

INSERT INTO `sys_dict_data` (`dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`, `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`) VALUES
(1, '中英文', 'ch', 'merio_language', NULL, NULL, 'Y', '0', 'admin', NOW(), 'admin', NOW(), '默认值，包含 Chinese, English, Chinese Traditional'),
(2, '繁体、手写体', 'ch_server', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Chinese, English, Chinese Traditional, Japanese'),
(3, '纯英文', 'en', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 English'),
(4, '日文为主', 'japan', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Chinese, English, Chinese Traditional, Japanese'),
(5, '韩文', 'korean', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Korean, English'),
(6, '繁体中文为主', 'chinese_cht', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Chinese, English, Chinese Traditional, Japanese'),
(7, '泰米尔文', 'ta', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Tamil, English'),
(8, '泰卢固文', 'te', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Telugu, English'),
(9, '卡纳达文', 'ka', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Kannada'),
(10, '希腊文', 'el', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Greek, English'),
(11, '泰文', 'th', 'merio_language', NULL, NULL, 'N', '0', 'admin', NOW(), 'admin', NOW(), '包含 Thai, English')
ON DUPLICATE KEY UPDATE `dict_label` = VALUES(`dict_label`), `remark` = VALUES(`remark`);

-- ----------------------------
-- 7、大模型配置初始化
-- ----------------------------
-- DeepSeek Chat（TXT 转 Markdown 默认模型）
INSERT INTO `ai_models` (
    `model_code`, `model_name`, `provider`, `model_sort`, `api_key`, `base_url`,
    `model_type`, `max_tokens`, `temperature`, `support_reasoning`, `support_images`,
    `status`, `user_id`, `dept_id`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'deepseek-chat', 'DeepSeek Chat', 'openai', 1,
    'sk-你自己的key',
    'https://api.zetatechs.com/v1',
    'LLM', 4096, 0.7, 'N', 'N',
    '0', 1, 1, 'admin', NOW(), 'admin', NOW(), 'DeepSeek Chat模型'
WHERE NOT EXISTS (SELECT 1 FROM `ai_models` WHERE `model_code` = 'deepseek-chat');

-- qwen3-vl-plus（Stage4 图片描述模型）
INSERT INTO `ai_models` (
    `model_code`, `model_name`, `provider`, `model_sort`, `api_key`, `base_url`,
    `model_type`, `max_tokens`, `temperature`, `support_reasoning`, `support_images`,
    `status`, `user_id`, `dept_id`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'qwen3-vl-plus', 'Qwen3 VL Plus', 'openai', 2,
    'sk-你自己的key',
    'https://api.zetatechs.com/v1',
    'VLM', 4096, 0.7, 'N', 'Y',
    '0', 1, 1, 'admin', NOW(), 'admin', NOW(), 'Qwen3 VL Plus 图片描述模型'
WHERE NOT EXISTS (SELECT 1 FROM `ai_models` WHERE `model_code` = 'qwen3-vl-plus');

-- ----------------------------
-- 8、模型功能适配初始化
-- ----------------------------
INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`, `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    'TXT生成Markdown格式文档',
    'txt_to_markdown',
    (SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'deepseek-chat'),
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'txt_to_markdown' AND `del_flag` = '0'
);

INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`, `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    'Markdown图片生成描述',
    'md_image_description',
    (SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'qwen3-vl-plus'),
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'md_image_description' AND `del_flag` = '0'
);

-- ----------------------------
-- 9、注册 RAG 解析调度定时任务
-- ----------------------------
INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'RAG Stage2-A 链接申请失败兜底', 'default', 'default',
    'knowledge_content.tasks.document_parse_scheduler.stage2_path_a_job',
    '', '', '0 * * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每分钟扫描 LINK_FAILED 任务并重新申请上传链接'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job` WHERE `invoke_target` = 'knowledge_content.tasks.document_parse_scheduler.stage2_path_a_job');

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'RAG Stage2-B 上传失败兜底', 'default', 'default',
    'knowledge_content.tasks.document_parse_scheduler.stage2_path_b_job',
    '', '', '0 * * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每分钟扫描 UPLOAD_FAILED 分段并重试或标记超时'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job` WHERE `invoke_target` = 'knowledge_content.tasks.document_parse_scheduler.stage2_path_b_job');

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'RAG Stage3 解析结果轮询', 'default', 'default',
    'knowledge_content.tasks.document_parse_scheduler.stage3_poll_job',
    '', '', '0 * * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每分钟扫描 PARSING 任务并轮询 MinerU 结果'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job` WHERE `invoke_target` = 'knowledge_content.tasks.document_parse_scheduler.stage3_poll_job');

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'RAG Stage4 md 合并兜底', 'default', 'default',
    'knowledge_content.tasks.document_parse_scheduler.stage4_retry_job',
    '', '', '0 0/5 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每 5 分钟扫描 CONVERT_FAILED 记录并重新触发合并'
WHERE NOT EXISTS (SELECT 1 FROM `sys_job` WHERE `invoke_target` = 'knowledge_content.tasks.document_parse_scheduler.stage4_retry_job');

-- ----------------------------
-- 10、注册菜单与接口权限
-- ----------------------------
-- 新增「知识管理」一级目录
INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '知识管理', '0', '5', 'knowledge', NULL, '', '', 1, 0, 'M', '0', '0', '', 'knowledge', 'admin', NOW(), 'admin', NOW(), '知识管理目录'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0');

-- 新增「资料上传」二级菜单
INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '资料上传', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0'), '1', 'document', 'knowledge/document/index', '', '', 1, 0, 'C', '0', '0', 'rag:document:list', 'document', 'admin', NOW(), 'admin', NOW(), '资料上传菜单'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'document' AND `component` = 'knowledge/document/index');

-- 资料上传按钮权限
INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '资料上传', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'document' AND `component` = 'knowledge/document/index'), '1', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:document:upload', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:document:upload');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '资料删除', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'document' AND `component` = 'knowledge/document/index'), '2', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:document:remove', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:document:remove');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '资料预览', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'document' AND `component` = 'knowledge/document/index'), '3', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:document:preview', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:document:preview');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '资料下载', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'document' AND `component` = 'knowledge/document/index'), '4', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:document:download', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:document:download');

-- 模型适配菜单（直接挂载在AI管理下，不再作为模型管理的子菜单）
INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '模型适配', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'ai' AND `parent_id` = '0'), '3', 'model-adapter', 'ai/function-adapter/index', '', '', 1, 0, 'C', '0', '0', 'ai:model:function-adapter:list', 'tree', 'admin', NOW(), 'admin', NOW(), '模型适配菜单'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'model-adapter');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '适配新增', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'model-adapter'), '1', '', '', '', '', 1, 0, 'F', '0', '0', 'ai:model:function-adapter:add', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'ai:model:function-adapter:add');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '适配修改', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'model-adapter'), '2', '', '', '', '', 1, 0, 'F', '0', '0', 'ai:model:function-adapter:edit', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'ai:model:function-adapter:edit');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '适配删除', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'model-adapter'), '3', '', '', '', '', 1, 0, 'F', '0', '0', 'ai:model:function-adapter:remove', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'ai:model:function-adapter:remove');









