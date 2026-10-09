# RAGAS 指标全局实例不支持并发

2026-10-06。执行 10 的逐题明细里，18 道题缺了一两项分数，折线上是空点。采数是齐的，缺的是打分。

## 现象

执行 10 共 45 题，答案都有。缺分统计：

- 忠实度 13 题
- 精确度 8 题
- 相关性 1 题
- 召回率没有缺

第 23 题就是召回率 0.500，另外三项为空。打分日志里对应的是：

```text
AssertionError: llm must be set to compute score
AssertionError: Error: 'answer_relevancy' requires embeddings to be set.
AttributeError: 'NoneType' object has no attribute 'generate'
TimeoutError
```

RAGAS 默认不把单次指标任务的异常抛出来，失败的那一项记成空，其它项照常留下。

## 原因

`ragas.metrics` 里的 `context_recall`、`context_precision`、`faithfulness`、`answer_relevancy` 是模块级全局对象，各只有一份。

`ragas.evaluation.evaluate()` 打分时把对话模型和向量模型写到这些对象上，结束时在 `finally` 里再清成 `None`：

```python
if isinstance(metric, MetricWithLLM) and metric.llm is None:
    metric.llm = llm
...
finally:
    for i in llm_changed:
        metrics[i].llm = None
    for i in embeddings_changed:
        metrics[i].embeddings = None
```

一次 `evaluate()` 内部把四个指标并行打，这个 RAGAS 支持。两次 `evaluate()` 同时跑、又共用这四个全局对象，它不支持。先结束的那次会把模型擦掉，另一道题的指标任务还在读这张表，于是出现 `llm must be set`。

当时测评每批 4 题一起打分，代码直接传入这四个全局对象：

```python
from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

evaluate(
    ds,
    metrics=[context_recall, context_precision, faithfulness, answer_relevancy],
    llm=chat,
    embeddings=embeddings,
)
```

## 处理

按测评并发数缓存同样多套指标。当前每批 4 题，就准备 4 套。每套里四个指标各新建一份，共用一把锁。打分时领一套没被占用的，用完放开。

文件：`knowledge-admin/src/knowledge_admin/service/eval_metric_pool.py`。

调用点：`EvalTaskService._evaluate_sample`。套数跟 `EvalDatasetConfig.eval_run_batch_size` 走，改并发时一起变。
