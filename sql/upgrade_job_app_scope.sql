-- ----------------------------------------------------------------------------
-- 定时任务 app_scope 字段升级脚本
-- 适用于已有数据库环境（sys_job 和 sys_job_log 表已存在）
-- 创建时间: 2026-06-09
-- ----------------------------------------------------------------------------

-- 1. sys_job 表添加 app_scope 字段（如果尚未添加）
-- 注意：如果字段已存在，请先确认是否需要保留旧数据
ALTER TABLE sys_job ADD COLUMN app_scope varchar(64) DEFAULT 'knowledge-admin' COMMENT '任务所属应用（knowledge-admin/knowledge-rag/knowledge-agent）';

-- 2. sys_job_log 表添加 app_scope 字段（如果尚未添加）
ALTER TABLE sys_job_log ADD COLUMN app_scope varchar(64) DEFAULT 'knowledge-admin' COMMENT '任务所属应用';

-- 3. 更新 sys_job 表中 app_scope 为 NULL 或空字符串的记录（兼容旧数据）
UPDATE sys_job SET app_scope = 'knowledge-admin' WHERE app_scope IS NULL OR app_scope = '';

-- 4. 更新 sys_job_log 表中 app_scope 为 NULL 或空字符串的记录
UPDATE sys_job_log SET app_scope = 'knowledge-admin' WHERE app_scope IS NULL OR app_scope = '';

-- 5. 插入字典类型（如果不存在）
INSERT INTO sys_dict_type (dict_name, dict_type, status, create_by, create_time, remark)
SELECT '任务所属应用', 'sys_job_app_scope', '0', 'admin', NOW(), '定时任务所属应用列表'
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_type WHERE dict_type = 'sys_job_app_scope');

-- 6. 插入字典数据（如果不存在）
INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, remark)
SELECT 1, 'knowledge-admin', 'knowledge-admin', 'sys_job_app_scope', '', 'primary', 'Y', '0', 'admin', NOW(), '知识管理后台'
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_data WHERE dict_type = 'sys_job_app_scope' AND dict_value = 'knowledge-admin');

INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, remark)
SELECT 2, 'knowledge-rag', 'knowledge-rag', 'sys_job_app_scope', '', 'info', 'N', '0', 'admin', NOW(), '知识RAG服务'
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_data WHERE dict_type = 'sys_job_app_scope' AND dict_value = 'knowledge-rag');

INSERT INTO sys_dict_data (dict_sort, dict_label, dict_value, dict_type, css_class, list_class, is_default, status, create_by, create_time, remark)
SELECT 3, 'knowledge-agent', 'knowledge-agent', 'sys_job_app_scope', '', 'info', 'N', '0', 'admin', NOW(), '知识Agent服务'
WHERE NOT EXISTS (SELECT 1 FROM sys_dict_data WHERE dict_type = 'sys_job_app_scope' AND dict_value = 'knowledge-agent');
