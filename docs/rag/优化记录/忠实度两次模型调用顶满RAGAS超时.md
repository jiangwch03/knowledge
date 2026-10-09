# 忠实度两次模型调用顶满 RAGAS 超时

2026-10-07。执行 12 里部分题忠实度是空的，同一题的召回率、精确度、相关性有分。

## 现象

拿执行 12 里忠实度为空、且有上下文的 4 题，按线上同一条打分路径重跑。3 题第一次就打出 1.0。第 6 题「milvus有啥改进？」前两次被掐掉，第三次打出 0.99。

日志：

```text
00:23:37  Exception raised in Job[2]: TimeoutError()
00:26:39  Exception raised in Job[0]: TimeoutError()
00:29:40  [忠实度] 得分 0.9876543209876543 q=milvus有啥改进？
```

`Job[2]` 是四个指标里的忠实度。两次失败都卡在整 180.01 秒。模型那几次都返回了 200，没有 429，也不是 `APIConnectionError`。

## 原因

忠实度一题要串行打两次模型：先从答案抽出陈述，再逐条判断这些陈述有没有依据。RAGAS 用 `asyncio.wait_for` 把整项包住，时限是 `RunConfig.timeout`，默认 180 秒。两次调用加起来超过 180 秒，整项记成空分。

这不是单次 HTTP 超时。对话模型没有单独设请求超时，走 OpenAI 客户端默认值：整次请求 600 秒，建立连接 5 秒。HTTP 超时报的是 `Request timed out`，这次日志是普通的 `TimeoutError()`。

缺分后再打一遍的外层重试走的还是这 180 秒，长答案会再超时一次，空分补不回来。

## 处理

单题单个指标的时限改成 360 秒，配置项 `eval_metric_timeout_seconds`。召回率、精确度、忠实度、相关性走同一个 `RunConfig(timeout=...)`。裁判模型和向量模型的 HTTP 连接、读取、写入、连接池等待也用这 360 秒。外层缺分重试删掉。

文件：`knowledge-common/src/knowledge_common/config/env.py`、`knowledge-common/src/knowledge_common/common/factory/langchain_model_factory.py`、`knowledge-admin/src/knowledge_admin/service/eval_task_service.py`。

管理端重启后生效。已经在跑的执行仍用旧的 180 秒。
