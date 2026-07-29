-- =============================================================================
-- 03_upgrade_knowledge_retrieval.sql
-- knowledge-retrieval 种子：主题字典 / Tavily 占位参数 / 菜单权限 / 模型适配
-- 可重复执行（WHERE NOT EXISTS）；禁止写入真实 Tavily Key
-- =============================================================================

-- ========== 主题字典 ==========
INSERT INTO `sys_dict_type` (
    `dict_name`, `dict_type`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '知识检索主题', 'rag_retrieve_topic', '0', 'admin', NOW(), 'admin', NOW(),
       '知识问答 topic_gate 主题列表（文档不强制绑 topic）'
WHERE NOT EXISTS (SELECT 1 FROM `sys_dict_type` WHERE `dict_type` = 'rag_retrieve_topic');

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 1, 'Milvus技术', 'milvus', 'rag_retrieve_topic', '', 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_dict_data` WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'milvus');

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 2, 'AI制作', 'ai_production', 'rag_retrieve_topic', '', 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_dict_data` WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'ai_production');

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 3, 'LangChain技术', 'langchain', 'rag_retrieve_topic', '', 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_dict_data` WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'langchain');

INSERT INTO `sys_dict_data` (
    `dict_sort`, `dict_label`, `dict_value`, `dict_type`, `css_class`, `list_class`,
    `is_default`, `status`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 4, 'LangGraph技术', 'langgraph', 'rag_retrieve_topic', '', 'default', 'N', '0', 'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_dict_data` WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'langgraph');

-- 已存在时同步中文标签（可重复执行）
UPDATE `sys_dict_data` SET `dict_label` = 'Milvus技术', `update_by` = 'admin', `update_time` = NOW()
WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'milvus';
UPDATE `sys_dict_data` SET `dict_label` = 'AI制作', `update_by` = 'admin', `update_time` = NOW()
WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'ai_production';
UPDATE `sys_dict_data` SET `dict_label` = 'LangChain技术', `update_by` = 'admin', `update_time` = NOW()
WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'langchain';
UPDATE `sys_dict_data` SET `dict_label` = 'LangGraph技术', `update_by` = 'admin', `update_time` = NOW()
WHERE `dict_type` = 'rag_retrieve_topic' AND `dict_value` = 'langgraph';

-- ========== Tavily Key 占位（空，管理员自行填写） ==========
INSERT INTO `sys_config` (
    `config_name`, `config_key`, `config_value`, `config_type`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT 'Tavily API Key', 'rag.tavily.api_key', '', 'N',
       'admin', NOW(), 'admin', NOW(), '知识问答联网搜索 Key；留空则 Tool 友好降级。禁止把真实 Key 写入仓库 SQL。'
WHERE NOT EXISTS (SELECT 1 FROM `sys_config` WHERE `config_key` = 'rag.tavily.api_key');

-- ========== 精排/分片单文档字符上限 ==========
-- qwen3-rerank 官方约 4000 tokens/条；此处为字符侧安全帽，同时约束 Embedding 块大小
INSERT INTO `sys_config` (
    `config_name`, `config_key`, `config_value`, `config_type`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '精排单文档最大字符数', 'rag.rerank.max_doc_chars', '4000', 'N',
       'admin', NOW(), 'admin', NOW(),
       '精排截断与 Embedding 分片 chunkSize 上限（字符）。对齐 qwen3-rerank 约 4000 tokens/条（中文约 1 字/token）。'
WHERE NOT EXISTS (SELECT 1 FROM `sys_config` WHERE `config_key` = 'rag.rerank.max_doc_chars');

-- 已存在时同步默认值与备注（可重复执行）
UPDATE `sys_config`
SET `config_value` = '4000',
    `remark` = '精排截断与 Embedding 分片 chunkSize 上限（字符）。对齐 qwen3-rerank 约 4000 tokens/条（中文约 1 字/token）。',
    `update_by` = 'admin',
    `update_time` = NOW()
WHERE `config_key` = 'rag.rerank.max_doc_chars'
  AND `config_value` IN ('', '2000');

-- ========== 菜单：知识问答 ==========
INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '知识问答',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'knowledge' AND `parent_id` = '0'),
       '5', 'qa', 'knowledge/qa/index', '', '',
       1, 0, 'C', '0', '0', 'rag:retrieve:list', 'message',
       'admin', NOW(), 'admin', NOW(), '知识问答会话页'
WHERE NOT EXISTS (
    SELECT 1 FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'
);

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '会话管理',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '1', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:session', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:session');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '会话查询',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '2', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:session:list', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:session:list');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '会话新增',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '3', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:session:add', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:session:add');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '会话修改',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '4', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:session:edit', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:session:edit');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '会话删除',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '5', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:session:remove', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:session:remove');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '会话详情',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '6', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:session:query', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:session:query');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '问答聊天',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '7', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:chat', '#',
       'admin', NOW(), 'admin', NOW(), ''
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:chat');

INSERT INTO `sys_menu` (
    `menu_name`, `parent_id`, `order_num`, `path`, `component`, `query`, `route_name`,
    `is_frame`, `is_cache`, `menu_type`, `visible`, `status`, `perms`, `icon`,
    `create_by`, `create_time`, `update_by`, `update_time`, `remark`
)
SELECT '混合检索',
       (SELECT `menu_id` FROM `sys_menu` WHERE `path` = 'qa' AND `component` = 'knowledge/qa/index'),
       '8', '', '', '', '',
       1, 0, 'F', '0', '0', 'rag:retrieve:query', '#',
       'admin', NOW(), 'admin', NOW(), 'POST /retrieval/search'
WHERE NOT EXISTS (SELECT 1 FROM `sys_menu` WHERE `perms` = 'rag:retrieve:query');

-- 给 admin 角色授权（role_id=1）
INSERT INTO `sys_role_menu` (`role_id`, `menu_id`)
SELECT 1, m.menu_id
FROM `sys_menu` m
WHERE m.perms IN (
    'rag:retrieve:list',
    'rag:retrieve:session',
    'rag:retrieve:session:list',
    'rag:retrieve:session:add',
    'rag:retrieve:session:edit',
    'rag:retrieve:session:remove',
    'rag:retrieve:session:query',
    'rag:retrieve:chat',
    'rag:retrieve:query'
)
AND NOT EXISTS (
    SELECT 1 FROM `sys_role_menu` rm WHERE rm.role_id = 1 AND rm.menu_id = m.menu_id
);

-- ========== 精排模型种子（默认不启用；QA/search 传 enableRerank=true 且配好 Key 后生效） ==========
-- 推荐：通义 qwen3-rerank（对齐开源 Qwen3-Reranker，性价比优先 1.5B 档能力）
INSERT INTO `ai_models` (
    `model_code`, `model_name`, `provider`, `model_sort`, `api_key`, `base_url`,
    `model_type`, `max_tokens`, `temperature`, `support_reasoning`, `support_images`,
    `status`, `user_id`, `dept_id`, `create_by`, `create_time`, `update_by`, `update_time`, `remark`
) SELECT
    'qwen3-rerank', '通义千问 Qwen3-Rerank', 'DashScope', 5,
    'sk-你自己的key',
    'https://dashscope.aliyuncs.com/api/v1',
    'rerank', NULL, NULL, 'N', 'N',
    '0', 1, 1, 'admin', NOW(), 'admin', NOW(),
    '检索精排；开源对照 Qwen3-Reranker-1.5B-Instruct。禁止把真实 Key 写入仓库。'
WHERE NOT EXISTS (SELECT 1 FROM `ai_models` WHERE `model_code` = 'qwen3-rerank');

INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`,
    `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    '知识检索精排',
    'document_rerank',
    CAST((SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'qwen3-rerank') AS CHAR),
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'document_rerank' AND `del_flag` = '0'
);

-- ========== 知识问答 Agent 模型适配（下拉选项来源） ==========
-- param_id 必须与 AiModelFunctionAdapterConfig.knowledge_qa_agent_param_id 一致
-- 优先复用网页爬取 Agent 已绑定的聊天模型；否则回退 qwen-plus / deepseek-chat
INSERT INTO `knowledge_ai_model_function_adapter` (
    `function_point`, `param_id`, `model_id`,
    `create_by`, `create_time`, `update_by`, `update_time`
) SELECT
    '知识问答Agent',
    'knowledge_qa_agent',
    CAST(COALESCE(
        (SELECT `model_id` FROM `knowledge_ai_model_function_adapter`
         WHERE `param_id` = 'web_crawler_agent' AND `del_flag` = '0' LIMIT 1),
        (SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'qwen-plus' LIMIT 1),
        (SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'deepseek-chat' LIMIT 1)
    ) AS CHAR),
    'admin', NOW(), 'admin', NOW()
WHERE NOT EXISTS (
    SELECT 1 FROM `knowledge_ai_model_function_adapter`
    WHERE `param_id` = 'knowledge_qa_agent' AND `del_flag` = '0'
)
AND COALESCE(
    (SELECT `model_id` FROM `knowledge_ai_model_function_adapter`
     WHERE `param_id` = 'web_crawler_agent' AND `del_flag` = '0' LIMIT 1),
    (SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'qwen-plus' LIMIT 1),
    (SELECT `model_id` FROM `ai_models` WHERE `model_code` = 'deepseek-chat' LIMIT 1)
) IS NOT NULL;
