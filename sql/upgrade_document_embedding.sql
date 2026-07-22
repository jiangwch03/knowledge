-- =============================================================================
-- 独立升级：文档切分与向量化（最终表结构 / 菜单 / 调度 / 字典，可重复执行）
--
-- 前置：建议先执行 sql/upgrade_document_embedding_adapter.sql（dimensions 适配）
-- 覆盖：embedding_task、segment、segment_archive、调度、菜单、分隔符/正则字典
-- 执行：mysql ... --default-character-set=utf8mb4 < this.sql
-- =============================================================================

SET NAMES utf8mb4;

-- A. embedding 任务表（不含 release_tag）
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

-- B. segment 表（release_tag 权威在此，与 Milvus 对齐）
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

-- B'. segment 归档表（主表物理删除前快照）
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

-- C. 调度兜底（PENDING 重投 + 僵尸续跑 + FAILED 自动重试）
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

-- 临时：自动发布 + pending_delete 清理（正式发布 UI 上线后可停用）
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

-- D. 菜单与权限（知识管理下）
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

-- =============================================================================
-- E. 分隔符切分系统字典（document_split_separator）
-- dict_value 存可见转义串（\n\n / \t / \u0020），切分时再解码；避免管理页显示空白
-- =============================================================================

INSERT INTO `sys_dict_type` (
    `dict_name`, `dict_type`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
    '文档切分分隔符',
    'document_split_separator',
    '0',
    'admin',
    NOW(),
    'admin',
    NOW(),
    'SEPARATOR 策略可选字面量分隔符；dict_value 为可见转义串（如 \\n\\n），切分前解码'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_type` WHERE `dict_type` = 'document_split_separator'
);

-- 兼容：把早期写入的真实控制字符迁移为可见转义串
UPDATE `sys_dict_data`
SET `dict_value` = '\\n\\n', `update_time` = NOW()
WHERE `dict_type` = 'document_split_separator' AND `dict_value` = CONCAT(CHAR(10), CHAR(10));

UPDATE `sys_dict_data`
SET `dict_value` = '\\n', `update_time` = NOW()
WHERE `dict_type` = 'document_split_separator' AND `dict_value` = CHAR(10);

UPDATE `sys_dict_data`
SET `dict_value` = '\\t', `update_time` = NOW()
WHERE `dict_type` = 'document_split_separator' AND `dict_value` = CHAR(9);

UPDATE `sys_dict_data`
SET `dict_value` = '\\u0020', `update_time` = NOW()
WHERE `dict_type` = 'document_split_separator' AND `dict_value` = ' ';

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 1, '空行（\\n\\n）', '\\n\\n', 'document_split_separator',
       NULL, 'default', 'Y', '0', 'admin', NOW(), 'admin', NOW(), '两个换行'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '\\n\\n'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 2, '换行（\\n）', '\\n', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '单个换行'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '\\n'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 3, '制表符（\\t）', '\\t', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), 'Tab'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '\\t'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 4, '空格', '\\u0020', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '单个空格'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '\\u0020'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 5, '中文句号（。）', '。', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '。'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 6, '中文感叹号（！）', '！', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '！'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 7, '中文问号（？）', '？', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '？'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 8, '中文分号（；）', '；', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '；'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 9, '中文逗号（，）', '，', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '，'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 10, '英文句号（.）', '.', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '.'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 11, '竖线（|）', '|', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), NULL
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '|'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 12, '分隔线（---）', '---', 'document_split_separator',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), 'Markdown 分隔线'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_separator' AND `dict_value` = '---'
);

-- =============================================================================
-- F. 正则切分常用模板字典（document_split_regex_template）
-- dict_value 存可直接交给 re.compile / re.split 的 pattern（含 \\n 等可见转义）
-- =============================================================================

INSERT INTO `sys_dict_type` (
    `dict_name`, `dict_type`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT
    '文档切分正则模板',
    'document_split_regex_template',
    '0',
    'admin',
    NOW(),
    'admin',
    NOW(),
    'REGEX 策略常用模板；dict_value 为正则表达式，可选后仍可手改'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_type` WHERE `dict_type` = 'document_split_regex_template'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 1, '中文句末标点', '[。！？]', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '中文段落/口语稿'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '[。！？]'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 2, '中文分句（含分号）', '[。！？；]', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '切点更密，靠块大小合并'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '[。！？；]'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 3, '英文句末', '[.!?]+', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '英文纯文本'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '[.!?]+'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 4, '空行（可变）', '\\n\\s*\\n+', 'document_split_regex_template',
       NULL, 'default', 'Y', '0', 'admin', NOW(), 'admin', NOW(), '比恰好两个换行更稳'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '\\n\\s*\\n+'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 5, '空行或分隔线', '\\n\\s*\\n+|---+', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '空行或 --- 均切开'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '\\n\\s*\\n+|---+'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 6, '题号（数字）', '(?=\\n\\d+[\\.、]\\s)', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '前瞻保留 1. / 1、'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '(?=\\n\\d+[\\.、]\\s)'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 7, '题号（中文序号）', '(?=\\n[一二三四五六七八九十百]+、\\s*)', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '前瞻保留一、二、'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '(?=\\n[一二三四五六七八九十百]+、\\s*)'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 8, 'FAQ 问句标记', '(?=\\n(?:Q[:：]|问[：:]\\s*))', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '在 Q: / 问： 前切开'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '(?=\\n(?:Q[:：]|问[：:]\\s*))'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 9, '日志时间戳行', '(?=\\n\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}:\\d{2})', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '每条日志一块起点'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '(?=\\n\\d{4}-\\d{2}-\\d{2}[ T]\\d{2}:\\d{2}:\\d{2})'
);

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 10, '章节（第N章）', '(?=\\n第[一二三四五六七八九十百零〇\\d]+章)', 'document_split_regex_template',
       NULL, 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), '非 Markdown 书籍体'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_dict_data`
    WHERE `dict_type` = 'document_split_regex_template' AND `dict_value` = '(?=\\n第[一二三四五六七八九十百零〇\\d]+章)'
);
