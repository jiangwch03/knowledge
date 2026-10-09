"""指标套池：同一套不会同时借给两道题。"""

from __future__ import annotations

import threading

from knowledge_admin.infra.ragas_vertex_compat import ensure_ragas_vertex_chat
from knowledge_admin.service.eval_metric_pool import EvalMetricSuitePool, build_answer_relevancy


class _FakeSuite:
    def __init__(self, name: str) -> None:
        self.name = name
        self.lock = threading.Lock()

    def metrics(self) -> list:
        return [self.name]


def test_answer_relevancy_keeps_concrete_answers() -> None:
    ensure_ragas_vertex_chat()
    metric = build_answer_relevancy()
    examples = metric.question_generation.examples
    flags = [example[1].noncommittal for example in examples]
    assert flags == [0, 1, 0, 1]
    assert '根据知识库资料' in metric.question_generation.instruction


def test_borrow_hands_out_different_suites() -> None:
    pool = EvalMetricSuitePool([_FakeSuite('a'), _FakeSuite('b')])
    with pool.borrow() as first, pool.borrow() as second:
        assert first.name != second.name


def test_borrow_waits_until_a_suite_is_free() -> None:
    pool = EvalMetricSuitePool([_FakeSuite('only')])
    started = threading.Event()
    finished = threading.Event()
    holder = pool.borrow()
    held = holder.__enter__()

    def _wait_then_take() -> None:
        started.set()
        with pool.borrow() as suite:
            assert suite is held
            finished.set()

    worker = threading.Thread(target=_wait_then_take)
    worker.start()
    assert started.wait(1)
    assert not finished.wait(0.2)
    holder.__exit__(None, None, None)
    worker.join(1)
    assert finished.is_set()
    assert not worker.is_alive()
