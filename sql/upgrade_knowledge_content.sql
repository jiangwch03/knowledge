-- ----------------------------------------------------------------------------
-- knowledge-content 全量升级脚本（合并版）
--
-- 合并自：
--   upgrade_rag_document_upload.sql
--   upgrade_web_crawler_agent.sql
--   （及其历史拆分脚本：agent_chat / crawl_proxy_pool / task_version 等）
--
-- 覆盖：资料上传 + MinerU 解析、文档主表/文件子表、网页爬取 Agent
-- 适用：新环境全量初始化（最终表结构直接写在 CREATE 中；可重复执行）
-- 创建时间: 2026-07-16
-- ----------------------------------------------------------------------------

-- ============================================================================
-- A. 文档域：主表 / 文件子表 / 上传与 MinerU
-- ============================================================================

-- A.1 文档主表（文件级字段见 knowledge_document_file）
CREATE TABLE IF NOT EXISTS `knowledge_document` (
    `doc_id` bigint NOT NULL AUTO_INCREMENT COMMENT '文档主键',
    `task_id` bigint DEFAULT NULL COMMENT '关联任务ID（source_type=0时为上传任务ID，source_type=1时为爬取任务ID）',
    `source_type` char(1) DEFAULT '0' COMMENT '来源类型（0-手动上传 1-网页爬取）',
    `doc_title` varchar(255) NOT NULL COMMENT '文档标题',
    `doc_desc` varchar(500) DEFAULT NULL COMMENT '文档描述',
    `doc_version` varchar(20) DEFAULT '1.0' COMMENT '文档版本',
    `is_latest` char(1) DEFAULT '1' COMMENT '是否最新版本（0-否 1-是）',
    `version_remark` varchar(255) DEFAULT NULL COMMENT '版本说明',
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档主表（文件级字段见 knowledge_document_file）';

-- A.2 文档文件子表
CREATE TABLE IF NOT EXISTS `knowledge_document_file` (
    `id` bigint NOT NULL AUTO_INCREMENT COMMENT '文件行主键',
    `doc_id` bigint NOT NULL COMMENT '关联 knowledge_document.doc_id',
    `task_id` bigint DEFAULT NULL COMMENT '冗余任务ID（上传任务或爬取任务）',
    `doc_name` varchar(255) DEFAULT NULL COMMENT '文件名',
    `doc_type` varchar(50) DEFAULT NULL COMMENT '文档格式 PDF/DOC/DOCX/XLSX/MD',
    `source_url` text COMMENT '与 doc_key 对应的原始网页URL（上传可空）',
    `original_doc_key` varchar(500) DEFAULT NULL COMMENT '原始上传文件MinIO对象键',
    `doc_key` varchar(500) DEFAULT NULL COMMENT '最终Markdown MinIO对象键',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    PRIMARY KEY (`id`),
    KEY `idx_doc_id` (`doc_id`),
    KEY `idx_task_id` (`task_id`),
    KEY `idx_doc_id_del` (`doc_id`, `del_flag`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档文件子表';

-- A.3 文档上传任务表
CREATE TABLE IF NOT EXISTS `knowledge_upload_document_parse_task` (
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

-- A.4 MinerU 解析任务表
CREATE TABLE IF NOT EXISTS `knowledge_mineru_parse_task` (
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

-- A.5 MinerU 解析批次/分段明细表
CREATE TABLE IF NOT EXISTS `knowledge_mineru_parse_detail_task` (
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

-- A.6 模型功能适配表
CREATE TABLE IF NOT EXISTS `knowledge_ai_model_function_adapter` (
    `adapter_id` bigint NOT NULL AUTO_INCREMENT COMMENT '适配ID',
    `function_point` varchar(100) NOT NULL COMMENT '业务功能点',
    `param_id` varchar(64) NOT NULL COMMENT '参数ID，唯一标识业务功能',
    `model_id` varchar(500) NOT NULL COMMENT '关联模型ID，多个用|分隔',
    `dimensions` int DEFAULT NULL COMMENT '向量维度（Embedding 业务适配必填，如 document_embedding）',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    PRIMARY KEY (`adapter_id`),
    UNIQUE KEY `uk_param_id` (`param_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='模型功能适配表';

-- A.7 Embedding 任务表（不含 release_tag；权威在 segment ↔ Milvus）
CREATE TABLE IF NOT EXISTS `knowledge_document_embedding_task` (
    `task_id` bigint NOT NULL AUTO_INCREMENT COMMENT '任务主键',
    `doc_id` bigint NOT NULL COMMENT '关联文档',
    `source_type` char(1) DEFAULT '0' COMMENT '来源类型（0-手动上传 1-网页爬取）',
    `split_type` varchar(32) NOT NULL COMMENT '切分策略 TITLE/LENGTH/SEPARATOR/REGEX/SMART',
    `split_params` text COMMENT '切分参数 JSON 快照',
    `status` varchar(32) DEFAULT 'PENDING' COMMENT 'PENDING/CHUNKING/EMBEDDING/COMPLETED/CHUNK_FAILED/EMBED_FAILED',
    `error_message` varchar(2000) DEFAULT NULL COMMENT '失败原因',
    `chunk_count` int DEFAULT '0' COMMENT '需入向量库的 segment 数（不含 skip_embedding 父片）',
    `embedded_count` int DEFAULT '0' COMMENT '成功写入 Milvus 的条数',
    `embedding_model_code` varchar(128) DEFAULT NULL COMMENT 'Embedding 模型编码快照',
    `dimensions` int DEFAULT NULL COMMENT '向量维度快照',
    `user_id` bigint NOT NULL COMMENT '提交用户ID',
    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    `remark` varchar(500) DEFAULT NULL COMMENT '备注',
    PRIMARY KEY (`task_id`),
    KEY `idx_doc_id` (`doc_id`),
    KEY `idx_status` (`status`),
    KEY `idx_create_time` (`create_time`),
    KEY `idx_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档 Embedding 任务表';

-- A.8 文档分段表（release_tag 与 Milvus 对齐）
CREATE TABLE IF NOT EXISTS `knowledge_document_segment` (
    `id` bigint NOT NULL AUTO_INCREMENT COMMENT '行主键',
    `task_id` bigint NOT NULL COMMENT '所属 embedding 任务',
    `doc_id` bigint NOT NULL COMMENT '所属文档',
    `file_id` bigint NOT NULL COMMENT '所属 knowledge_document_file.id',
    `chunk_id` varchar(64) NOT NULL COMMENT '业务分片 ID',
    `chunk_order` int NOT NULL COMMENT '任务内全局递增序号，从 0 起',
    `text` longtext COMMENT '分段正文',
    `metadata` text COMMENT '元数据 JSON',
    `parent_chunk_id` varchar(64) DEFAULT NULL COMMENT '子片指向父；无则空',
    `skip_embedding` tinyint DEFAULT '0' COMMENT '1=父片不进向量库；0=需要',
    `embedding_id` varchar(64) DEFAULT NULL COMMENT 'Milvus 主键；未写入为空',
    `embedding_vector` mediumblob DEFAULT NULL COMMENT 'Embedding 向量 float32 打包；刷入 Milvus 后可保留',
    `status` varchar(32) DEFAULT 'STORED' COMMENT 'STORED/EMBEDDED/VECTOR_STORED',
    `release_tag` varchar(32) NOT NULL DEFAULT 'canary' COMMENT 'canary/prod/pending_delete，与 Milvus 对齐',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '删除标志（0-未删除 2-已删除）',
    PRIMARY KEY (`id`),
    KEY `idx_task_id` (`task_id`),
    KEY `idx_doc_id` (`doc_id`),
    KEY `idx_doc_release` (`doc_id`, `release_tag`),
    KEY `idx_chunk_id` (`chunk_id`),
    KEY `idx_embedding_id` (`embedding_id`),
    KEY `idx_task_embed_queue` (`task_id`, `skip_embedding`, `status`, `del_flag`, `file_id`, `chunk_order`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档分段表';

CREATE TABLE IF NOT EXISTS `knowledge_document_segment_archive` (
    `id` bigint NOT NULL COMMENT '原 knowledge_document_segment.id',
    `task_id` bigint NOT NULL COMMENT '所属 embedding 任务',
    `doc_id` bigint NOT NULL COMMENT '所属文档',
    `file_id` bigint NOT NULL COMMENT '所属 knowledge_document_file.id',
    `chunk_id` varchar(64) NOT NULL COMMENT '业务分片 ID',
    `chunk_order` int NOT NULL COMMENT '文件内递增序号，从 0 起',
    `text` longtext COMMENT '分段正文',
    `metadata` text COMMENT '元数据 JSON',
    `parent_chunk_id` varchar(64) DEFAULT NULL COMMENT '子片指向父；无则空',
    `skip_embedding` tinyint DEFAULT '0' COMMENT '1=父片不进向量库；0=需要',
    `embedding_id` varchar(64) DEFAULT NULL COMMENT 'Milvus 主键；未写入为空',
    `embedding_vector` mediumblob DEFAULT NULL COMMENT 'Embedding 向量 float32 打包',
    `status` varchar(32) DEFAULT 'STORED' COMMENT 'STORED/EMBEDDED/VECTOR_STORED',
    `release_tag` varchar(32) NOT NULL DEFAULT 'canary' COMMENT '归档时标签',
    `create_by` varchar(64) DEFAULT '' COMMENT '创建者',
    `create_time` datetime DEFAULT NULL COMMENT '创建时间',
    `update_by` varchar(64) DEFAULT '' COMMENT '更新者',
    `update_time` datetime DEFAULT NULL COMMENT '更新时间',
    `del_flag` char(1) DEFAULT '0' COMMENT '归档时删除标志快照',
    `archive_time` datetime NOT NULL COMMENT '归档时间',
    `archive_by` varchar(64) DEFAULT '' COMMENT '归档操作者',
    `archive_reason` varchar(64) DEFAULT '' COMMENT '归档原因：pending_delete_cleanup / task_residue',
    PRIMARY KEY (`id`),
    KEY `idx_archive_task_id` (`task_id`),
    KEY `idx_archive_doc_id` (`doc_id`),
    KEY `idx_archive_time` (`archive_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='文档分段归档表';

-- ============================================================================
-- B. 网页爬取 Agent：会话 / 任务 / URL 记录
-- ============================================================================

-- B.1 Agent 会话 / 消息表
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

-- B.2 爬取任务表
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

-- B.3 爬取任务 URL 记录表
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

-- B.4 清理废弃表
DROP TABLE IF EXISTS `knowledge_web_crawler_message_task`;

-- ============================================================================
-- C. 字典初始化
-- ============================================================================

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
-- D. 模型与功能适配初始化
-- ============================================================================

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

-- ============================================================================
-- E. 定时任务
-- ============================================================================

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

DELETE FROM `sys_job`
WHERE `invoke_target` IN (
    'knowledge_content.tasks.embedding_task_scheduler.embedding_pending_repost_job',
    'knowledge_content.tasks.embedding_task_scheduler.embedding_stuck_timeout_job'
);

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'Embedding 任务兜底', 'default', 'default',
    'knowledge_content.tasks.embedding_task_scheduler.embedding_task_fallback_job',
    '', '', '0 */2 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(), '每2分钟：PENDING 重投；僵尸 CHUNKING/EMBEDDING 续跑；FAILED 自动重试'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.embedding_task_scheduler.embedding_task_fallback_job'
);

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'Embedding 临时自动发布', 'default', 'default',
    'knowledge_content.tasks.embedding_task_scheduler.embedding_auto_publish_job',
    '', '', '0 */5 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(),
    '临时：每5分钟将 COMPLETED+canary 发布为 prod，同 doc 旧 prod → pending_delete'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.embedding_task_scheduler.embedding_auto_publish_job'
);

INSERT INTO `sys_job` (
    `job_name`, `job_group`, `job_executor`, `invoke_target`, `job_args`, `job_kwargs`,
    `cron_expression`, `misfire_policy`, `concurrent`, `status`, `app_scope`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'Embedding pending_delete 清理', 'default', 'default',
    'knowledge_content.tasks.embedding_task_scheduler.embedding_pending_delete_cleanup_job',
    '', '', '0 */3 * * * ?', '3', '1', '0', 'knowledge-content',
    'admin', NOW(), 'admin', NOW(),
    '临时：每3分钟按批清理 pending_delete（删 Milvus + segment 归档并物理删除），默认每批 200'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_job`
    WHERE `invoke_target` = 'knowledge_content.tasks.embedding_task_scheduler.embedding_pending_delete_cleanup_job'
);

-- ============================================================================
-- F. 菜单与权限
-- ============================================================================

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '知识管理', '0', '5', 'knowledge', NULL, '', '', 1, 0, 'M', '0', '0', '', 'knowledge', 'admin', NOW(), 'admin', NOW(), '知识管理目录'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '资料上传', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0'), '1', 'document', 'knowledge/document/index', '', '', 1, 0, 'C', '0', '0', 'rag:document:list', 'document', 'admin', NOW(), 'admin', NOW(), '资料上传菜单'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'document' AND `component` = 'knowledge/document/index');

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

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT 'Embedding 任务', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0'), '3', 'embedding', 'knowledge/embedding/task/index', '', '', 1, 0, 'C', '0', '0', 'rag:embedding:list', 'chart', 'admin', NOW(), 'admin', NOW(), 'Embedding 任务菜单'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'embedding' AND `component` = 'knowledge/embedding/task/index');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT 'Embedding配置', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0'), '4', 'embedding-config', 'knowledge/embedding/config', '', '', 1, 0, 'C', '1', '0', 'rag:embedding:create', 'edit', 'admin', NOW(), 'admin', NOW(), 'Embedding 配置页（隐藏路由）'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `path` = 'embedding-config' AND `component` = 'knowledge/embedding/config');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '任务查询', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'embedding' AND `component` = 'knowledge/embedding/task/index'), '1', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:embedding:query', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:embedding:query');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '任务创建', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'embedding' AND `component` = 'knowledge/embedding/task/index'), '2', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:embedding:create', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:embedding:create' AND `menu_type` = 'F');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '任务重试', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'embedding' AND `component` = 'knowledge/embedding/task/index'), '3', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:embedding:retry', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:embedding:retry');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '任务删除', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'embedding' AND `component` = 'knowledge/embedding/task/index'), '4', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:embedding:remove', '#', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:embedding:remove');

INSERT INTO `sys_menu` (`menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`, `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`)
SELECT '任务发布', (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'embedding' AND `component` = 'knowledge/embedding/task/index'), '5', '', '', '', '', 1, 0, 'F', '0', '0', 'rag:embedding:publish', '#', 'admin', NOW(), 'admin', NOW(), '预留：发布切换'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:embedding:publish');

-- 文档向量化适配（dimensions / text-embedding-v4 / document_embedding）见：
--   sql/upgrade_document_embedding_adapter.sql
-- Embedding 字典（分隔符/正则模板）若未随本脚本完整写入，可补跑：
--   sql/upgrade_document_embedding.sql
