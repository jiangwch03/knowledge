-- ============================================================================
-- 对照本地 knoowledge.ai_models 现状：
--   - Profile 列已齐全
--   - 仅多出冗余列 context_window
--   - model_type 仍是 LLM/VLM 大写，字典是 llm/vlm
-- 本脚本可直接在客户端执行。
-- ============================================================================

-- 1) 若 max_input_tokens 为空，用旧上下文字段回填
UPDATE ai_models
SET max_input_tokens = context_window
WHERE max_input_tokens IS NULL
  AND context_window IS NOT NULL;

-- 2) 删除冗余上下文字段
ALTER TABLE ai_models DROP COLUMN context_window;

-- 3) model_type 对齐字典小写值
UPDATE ai_models SET model_type = 'llm' WHERE model_type = 'LLM';
UPDATE ai_models SET model_type = 'vlm' WHERE model_type = 'VLM';

-- 4) 字典中文标签区分 LLM / VLM（及 embedding / rerank）
UPDATE sys_dict_data
SET dict_label = 'LLM 大语言模型',
    remark = '纯文本对话/推理，不支持图像输入'
WHERE dict_type = 'ai_model_type' AND dict_value = 'llm';

UPDATE sys_dict_data
SET dict_label = 'VLM 视觉语言模型',
    remark = '多模态，支持图像+文本输入（看图理解）'
WHERE dict_type = 'ai_model_type' AND dict_value = 'vlm';

UPDATE sys_dict_data
SET dict_label = 'Embedding 向量模型',
    remark = '文本向量化，用于检索 Embedding'
WHERE dict_type = 'ai_model_type' AND dict_value = 'embedding';

UPDATE sys_dict_data
SET dict_label = 'Rerank 精排模型',
    remark = '检索结果精排打分'
WHERE dict_type = 'ai_model_type' AND dict_value = 'rerank';

-- 5) 核对
SHOW COLUMNS FROM ai_models;
SELECT model_id, model_code, model_type, max_tokens, max_input_tokens,
       support_reasoning, support_images, support_tool_call
FROM ai_models
ORDER BY model_id;
SELECT dict_label, dict_value, remark
FROM sys_dict_data
WHERE dict_type = 'ai_model_type'
ORDER BY dict_sort;
