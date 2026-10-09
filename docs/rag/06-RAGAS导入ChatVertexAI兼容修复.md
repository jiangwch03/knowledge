# RAGAS 导入 ChatVertexAI 的兼容修复

2026-09-25。测评集出题在分段拉取成功后失败，页面长期停在「出题中」。

## 现象

`knowledge-admin` 日志：

```text
ModuleNotFoundError: No module named 'langchain_community.chat_models.vertexai'
```

堆栈停在 `eval_dataset_generate_service._call_ragas` 的 `from ragas.llms import LangchainLLMWrapper`。失败后状态被写成出题失败，每分钟兜底又改回出题中，所以题目数一直是 0。

这不是测评集模型没配。适配 `eval_dataset` 已绑 `qwen-plus`，对话模型在进入 RAGAS 之前已经建好。

## 原因

当前版本：

- `ragas==0.4.3`（PyPI 最新）
- `langchain-community==0.4.2`

`ragas/llms/base.py` 在模块加载时无条件执行：

```python
from langchain_community.chat_models.vertexai import ChatVertexAI
```

`ChatVertexAI` 是 LangChain 里 Google Cloud Vertex AI 的对话封装。RAGAS 只把它放进「支持一次生成多条」的类型列表，出题和评分不会实例化它。

`langchain-community 0.4` 已把该模块从社区包拆出，磁盘上没有 `langchain_community/chat_models/vertexai.py`。项目使用 OpenAI 兼容的 `qwen-plus`，依赖里也没有 Vertex。升级 RAGAS 解决不了，最新版仍是这句导入。

## 修复

文件：`knowledge-admin/src/knowledge_admin/infra/ragas_vertex_compat.py`。

在 `import ragas` 之前调用 `ensure_ragas_vertex_chat()`。模块缺失时，用同名空类放进 `sys.modules['langchain_community.chat_models.vertexai']`。Python 按这个完整模块名先查导入缓存，命中后不再去 `site-packages` 找文件。真实模块若以后装回来，这段逻辑不会覆盖它。

调用点：

- `EvalDatasetGenerateService._call_ragas`（出题）
- `EvalTaskService._score_item`（四个指标评分）

占位类不发请求，也不替换 `eval_dataset` 适配的 `qwen-plus`。

## 生效

修改在进程内的导入缓存，已运行的 knowledge-admin 不会自动带上。重启后再出题，才会跳过这个导入错误。
