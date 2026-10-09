"""RAGAS 指标套缓存。

一次打分会同时改四个指标上的模型。默认那四个是全局对象，多题一起打会互相擦掉。
这里按测评并发数准备同样多套，每套四个指标共用一把锁。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Protocol

from knowledge_common.config.env import EvalDatasetConfig
from knowledge_common.utils.log_util import logger


class MetricSuite(Protocol):
    lock: threading.Lock

    def metrics(self) -> list:
        """这一套里的四个指标，顺序与打分结果列一致。"""


def build_answer_relevancy():
    """相关性。含糊只留给没给出内容的回答，避免把答到点子上的题乘成 0。"""
    from ragas.metrics._answer_relevance import (
        AnswerRelevancy,
        ResponseRelevanceInput,
        ResponseRelevanceOutput,
        ResponseRelevancePrompt,
    )

    class EvalAnswerRelevancyPrompt(ResponseRelevancePrompt):
        instruction = (
            '根据给出的回答反推它实际在回答的问题。'
            'noncommittal 为 1 只表示回答没有给出所问的事实：明确说不知道、没检索到、无法确认、没有找到，或只道歉、只改讲别的话题。'
            '回答里已经写出步骤、定义、名称、数值或结论时，noncommittal 为 0。'
            '开头的「根据知识库资料」和文中引用不算含糊。'
        )
        examples = [
            (
                ResponseRelevanceInput(response='Albert Einstein was born in Germany.'),
                ResponseRelevanceOutput(
                    question='Where was Albert Einstein born?',
                    noncommittal=0,
                ),
            ),
            (
                ResponseRelevanceInput(
                    response="I don't know about the smartphone invented in 2023.",
                ),
                ResponseRelevanceOutput(
                    question='What was the groundbreaking feature of the smartphone invented in 2023?',
                    noncommittal=1,
                ),
            ),
            (
                ResponseRelevanceInput(
                    response='根据知识库资料，在 Amazon EKS 上部署 Milvus 的步骤是创建集群、安装依赖并启动服务。',
                ),
                ResponseRelevanceOutput(
                    question='如何在 EKS 上部署 Milvus？',
                    noncommittal=0,
                ),
            ),
            (
                ResponseRelevanceInput(
                    response='很抱歉，当前知识库未检索到相关片段，无法确认这个问题。',
                ),
                ResponseRelevanceOutput(
                    question='这个问题的答案是什么？',
                    noncommittal=1,
                ),
            ),
        ]

    return AnswerRelevancy(question_generation=EvalAnswerRelevancyPrompt())


def _exception_chain(error: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = error
    seen = 0
    while current is not None and seen < 6:
        parts.append(f'{type(current).__name__}: {current}')
        current = current.__cause__ or current.__context__
        seen += 1
    return ' | '.join(parts)


def build_faithfulness():
    """忠实度。把空分时的原始异常打出来，RAGAS 默认只留一句 Connection error。"""
    from ragas.metrics._faithfulness import Faithfulness

    class LoggedFaithfulness(Faithfulness):
        async def _single_turn_ascore(self, sample, callbacks):
            question = (sample.user_input or '')[:40]
            try:
                score = await super()._single_turn_ascore(sample, callbacks)
            except Exception as error:
                logger.warning('[忠实度] 打分失败 q={} {}', question, _exception_chain(error))
                raise
            if score != score:
                logger.warning('[忠实度] 没有陈述，分数为空 q={}', question)
            else:
                logger.info('[忠实度] 得分 {} q={}', score, question)
            return score

    return LoggedFaithfulness()


class EvalMetricSuite:
    """召回率、精确度、忠实度、相关性各一份，由同一把锁保护。"""

    def __init__(self) -> None:
        from ragas.metrics._context_precision import ContextPrecision
        from ragas.metrics._context_recall import ContextRecall

        self.lock = threading.Lock()
        self._metrics = [
            ContextRecall(),
            ContextPrecision(),
            build_faithfulness(),
            build_answer_relevancy(),
        ]

    def metrics(self) -> list:
        return self._metrics


class EvalMetricSuitePool:
    """固定数量的指标套。领用时找一把还没被拿走的锁。"""

    def __init__(self, suites: list[MetricSuite]) -> None:
        if not suites:
            raise ValueError('指标套至少一套')
        self._suites = suites
        self._wait = threading.Condition()

    @contextmanager
    def borrow(self) -> Iterator[MetricSuite]:
        suite = self._acquire()
        try:
            yield suite
        finally:
            self._release(suite)

    def _acquire(self) -> MetricSuite:
        with self._wait:
            while True:
                for suite in self._suites:
                    if suite.lock.acquire(blocking=False):
                        return suite
                self._wait.wait()

    def _release(self, suite: MetricSuite) -> None:
        with self._wait:
            suite.lock.release()
            self._wait.notify()


_pool: EvalMetricSuitePool | None = None
_pool_guard = threading.Lock()


def get_metric_suite_pool() -> EvalMetricSuitePool:
    """进程内缓存。套数与测评每批题数相同。"""
    global _pool
    if _pool is not None:
        return _pool
    with _pool_guard:
        if _pool is None:
            from knowledge_admin.infra.ragas_vertex_compat import ensure_ragas_vertex_chat

            ensure_ragas_vertex_chat()
            size = max(1, int(EvalDatasetConfig.eval_run_batch_size))
            _pool = EvalMetricSuitePool([EvalMetricSuite() for _ in range(size)])
    return _pool
