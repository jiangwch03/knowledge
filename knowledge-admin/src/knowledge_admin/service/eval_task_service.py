"""测评任务：绑定测集+canary、异步 run、发布归档。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from knowledge_admin.enums.eval_dataset_status_enum import EvalDatasetStatus
from knowledge_admin.infra.rpc.content import EmbeddingService
from knowledge_admin.infra.rpc.retrieval import QaEvalService
from knowledge_admin.service.eval_dataset_generate_service import (
    EvalDatasetGenerateService,
    _run_on_ragas_loop,
)
from knowledge_admin.mapper.dao.eval_dataset_dao import EvalDatasetDao
from knowledge_admin.mapper.dao.eval_task_dao import EvalTaskDao
from knowledge_admin.mapper.do.eval_do import KnowledgeEvalRun, KnowledgeEvalRunItem, KnowledgeEvalTask
from knowledge_admin.vo.eval_vo import EvalDatasetSnapshotItemVo
from knowledge_admin.vo.eval_vo import (
    EvalItemScoreVo,
    EvalRunLaunchVo,
    EvalRunModel,
    EvalRunItemModel,
    EvalRunPageQueryModel,
    EvalRunPendingQuestionVo,
    EvalRunReportVo,
    EvalRunSummaryVo,
    EvalTaskCreateVo,
    EvalTaskListItemModel,
    EvalTaskModel,
    EvalTaskPageQueryModel,
    EvalTaskSwapDatasetVo,
)
from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.config.env import AiModelFunctionAdapterConfig, EvalDatasetConfig
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.exceptions.exception import ServiceException, ServiceWarning
from knowledge_common.facade.api.knowledge_content import ContentLabelQuery, PromoteTaskRequest
from knowledge_common.facade.api.knowledge_retrieval import EvalQaAnswerRequestVo
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.redis import DistributedLock, LockKey
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.langchain_model_vo import ChatModelConfigModel, EmbeddingModelConfigModel
from knowledge_common.vo.user_vo import CurrentUserModel


class EvalTaskService:
    """测评任务服务。"""

    @classmethod
    @transactional()
    async def create_task(
        cls,
        vo: EvalTaskCreateVo,
        current_user: CurrentUserModel,
    ) -> EvalTaskModel:
        dataset = await EvalDatasetDao.get_dataset_by_id(vo.dataset_id)
        if not dataset:
            raise ServiceException(message='测评集不存在')
        if dataset.status != EvalDatasetStatus.READY.value:
            raise ServiceException(message=f'测评集状态不可用: {dataset.status}')

        emb = await EmbeddingService.get_embedding_task(vo.embedding_task_id)
        if int(emb.doc_id) != int(dataset.doc_id):
            raise ServiceException(message='测评集与向量化任务文档不一致')
        if emb.status and str(emb.status).upper() != 'COMPLETED':
            raise ServiceException(message=f'向量化任务须为 COMPLETED，当前: {emb.status}')
        if emb.release_tag and str(emb.release_tag).lower() not in ('canary',):
            raise ServiceException(message=f'仅可绑定 canary 任务，当前 releaseTag={emb.release_tag}')

        now = datetime.now()
        user_name = current_user.user.user_name or ''
        task_name = vo.name.strip()
        if not task_name:
            raise ServiceException(message='请填写任务名称')
        task = KnowledgeEvalTask(
            name=task_name,
            embedding_task_id=vo.embedding_task_id,
            doc_id=int(dataset.doc_id),
            dataset_id=vo.dataset_id,
            status='OPEN',
            user_id=current_user.user.user_id,
            dept_id=current_user.user.dept_id,
            create_by=user_name,
            create_time=now,
            update_by=user_name,
            update_time=now,
            del_flag=DeleteFlag.NORMAL.value,
        )
        task = await EvalTaskDao.insert_task(task)
        return EvalTaskModel(**CamelCaseUtil.transform_result(task))

    @classmethod
    async def list_tasks(
        cls, query: EvalTaskPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        result = await EvalTaskDao.get_task_list(query, is_page=is_page)
        rows = result.rows if isinstance(result, PageModel) else result
        if isinstance(rows, list):
            await cls._fill_display_names(rows)
        return result

    @classmethod
    async def _fill_display_names(cls, rows: list[Any]) -> None:
        """列表里的文档、测评集、向量化任务补上名称，ID 仍保留。"""
        parsed = cls._parse_task_rows(rows)
        if not parsed:
            return
        dataset_names = await cls._dataset_name_map(parsed)
        doc_titles, split_labels = await cls._content_name_maps(parsed)
        for row, item in parsed:
            cls._write_display_names(row, item, dataset_names, doc_titles, split_labels)

    @classmethod
    def _parse_task_rows(cls, rows: list[Any]) -> list[tuple[dict[str, Any], EvalTaskListItemModel]]:
        parsed: list[tuple[dict[str, Any], EvalTaskListItemModel]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed.append((row, EvalTaskListItemModel.model_validate(row)))
        return parsed

    @classmethod
    async def _dataset_name_map(
        cls, parsed: list[tuple[dict[str, Any], EvalTaskListItemModel]]
    ) -> dict[int, str]:
        dataset_ids = sorted({item.dataset_id for _, item in parsed if item.dataset_id is not None})
        names = await EvalDatasetDao.list_names_by_ids(dataset_ids)
        return {item.dataset_id: item.name for item in names if item.name}

    @classmethod
    async def _content_name_maps(
        cls, parsed: list[tuple[dict[str, Any], EvalTaskListItemModel]]
    ) -> tuple[dict[int, str], dict[int, str]]:
        doc_ids = sorted({item.doc_id for _, item in parsed if item.doc_id is not None})
        task_ids = sorted({item.embedding_task_id for _, item in parsed if item.embedding_task_id is not None})
        if not doc_ids and not task_ids:
            return {}, {}
        try:
            labels = await EmbeddingService.list_content_labels(
                ContentLabelQuery(
                    doc_ids=','.join(str(doc_id) for doc_id in doc_ids),
                    task_ids=','.join(str(task_id) for task_id in task_ids),
                )
            )
        except ServiceException as exc:
            logger.warning('测评任务列表补名称失败: {}', exc)
            return {}, {}
        doc_titles = {item.doc_id: item.doc_title for item in labels.documents if item.doc_title}
        split_labels = {
            item.task_id: item.split_type_label
            for item in labels.embedding_tasks
            if item.split_type_label
        }
        return doc_titles, split_labels

    @classmethod
    def _write_display_names(
        cls,
        row: dict[str, Any],
        item: EvalTaskListItemModel,
        dataset_names: dict[int, str],
        doc_titles: dict[int, str],
        split_labels: dict[int, str],
    ) -> None:
        if item.dataset_id is not None:
            item.dataset_name = dataset_names.get(item.dataset_id)
        if item.doc_id is not None:
            item.doc_title = doc_titles.get(item.doc_id)
        if item.embedding_task_id is not None:
            item.embedding_split_label = split_labels.get(item.embedding_task_id)
        # 分页结果已是驼峰 dict，按列表项模型写回，去掉 BaseVo 上的 userInfo
        row.clear()
        row.update(item.model_dump(by_alias=True, exclude={'userInfo'}))

    @classmethod
    async def get_task(cls, eval_task_id: int) -> EvalTaskModel:
        task = await EvalTaskDao.get_task_by_id(eval_task_id)
        if not task:
            raise ServiceException(message='测评任务不存在')
        return EvalTaskModel(**CamelCaseUtil.transform_result(task))

    @classmethod
    def _ensure_open(cls, task: KnowledgeEvalTask) -> None:
        if task.status == 'ARCHIVED':
            raise ServiceException(message='任务已归档，禁止更换测集/跑测评/再次发布')

    @classmethod
    @transactional()
    async def swap_dataset(
        cls,
        eval_task_id: int,
        vo: EvalTaskSwapDatasetVo,
        current_user: CurrentUserModel,
    ) -> CrudResponseModel:
        task = await EvalTaskDao.get_task_by_id(eval_task_id)
        if not task:
            raise ServiceException(message='测评任务不存在')
        cls._ensure_open(task)
        dataset = await EvalDatasetDao.get_dataset_by_id(vo.dataset_id)
        if not dataset:
            raise ServiceException(message='测评集不存在')
        if int(dataset.doc_id) != int(task.doc_id):
            raise ServiceException(message='新测评集文档与任务不一致')
        if dataset.status != EvalDatasetStatus.READY.value:
            raise ServiceException(message=f'测评集状态不可用: {dataset.status}')
        await EvalTaskDao.update_task(
            {
                'eval_task_id': eval_task_id,
                'dataset_id': vo.dataset_id,
                'update_by': current_user.user.user_name or '',
                'update_time': datetime.now(),
            }
        )
        return CrudResponseModel(is_success=True, message='已更换测评集')

    @classmethod
    async def start_run(
        cls,
        eval_task_id: int,
        current_user: CurrentUserModel,
    ) -> EvalRunLaunchVo:
        # 锁没抢到说明进程还在跑。抢到了说明上次执行已经停了，可以续跑或新开。
        lock = DistributedLock(LockKey.eval_run_key(eval_task_id), expire=30, timeout=0, renew=True)
        if not await lock.acquire():
            raise ServiceWarning(message='测评正在执行中，请勿重复发起')
        handed = False
        try:
            launch = await cls._prepare_run(eval_task_id, current_user)
            asyncio.create_task(cls._execute_run_bg(launch, lock))
            handed = True
            return launch
        finally:
            if not handed:
                await lock.release()

    @classmethod
    @transactional()
    async def _prepare_run(
        cls,
        eval_task_id: int,
        current_user: CurrentUserModel,
    ) -> EvalRunLaunchVo:
        task = await EvalTaskDao.get_task_by_id(eval_task_id)
        if not task:
            raise ServiceException(message='测评任务不存在')
        cls._ensure_open(task)
        user_name = current_user.user.user_name or ''
        user_id = current_user.user.user_id
        if user_id is None:
            raise ServiceException(message='当前用户缺少 userId')

        unfinished = await EvalTaskDao.list_unfinished_runs(eval_task_id)
        if unfinished:
            latest = unfinished[0]
            for stale in unfinished[1:]:
                await cls._fail_run(int(stale.run_id), user_name, '执行进程已停止')
            return await cls._launch_existing(
                latest,
                update_by=user_name,
                user_id=int(user_id),
                message='上次执行已中断，已重新拉起',
            )

        dataset = await EvalDatasetDao.get_dataset_by_id(int(task.dataset_id))
        if not dataset or dataset.status != EvalDatasetStatus.READY.value:
            raise ServiceException(message='当前绑定测评集不可用')
        items = await EvalDatasetDao.list_items_by_dataset(int(task.dataset_id), enabled_only=True)
        if not items:
            raise ServiceException(message='无启用题目，无法跑测评')
        judge = await AiModelFunctionAdapterDao.get_adapter_by_param_id(
            AiModelFunctionAdapterConfig.eval_dataset_param_id
        )
        if judge is None or not judge.model_code:
            raise ServiceException(message='未配置测评集模型')
        snapshot = [
            EvalDatasetSnapshotItemVo(
                item_id=i.item_id,
                question=i.question or '',
                ground_truth=i.ground_truth or '',
                reference_excerpts=i.reference_excerpts,
                difficulty=i.difficulty,
                sort_order=i.sort_order,
            )
            for i in items
        ]
        now = datetime.now()
        run = KnowledgeEvalRun(
            eval_task_id=eval_task_id,
            dataset_id=int(task.dataset_id),
            embedding_task_id=int(task.embedding_task_id),
            release_tag='canary',
            status='PENDING',
            dataset_snapshot=json.dumps(
                [item.model_dump(by_alias=True) for item in snapshot],
                ensure_ascii=False,
            ),
            judge_model_code=judge.model_code,
            create_by=user_name,
            create_time=now,
            update_by=user_name,
            update_time=now,
            del_flag=DeleteFlag.NORMAL.value,
        )
        run = await EvalTaskDao.insert_run(run)
        pending = [
            EvalRunPendingQuestionVo(sort_order=idx, snap=item)
            for idx, item in enumerate(snapshot)
        ]
        return EvalRunLaunchVo(
            run=EvalRunModel(**CamelCaseUtil.transform_result(run)),
            message='评测已启动',
            run_id=int(run.run_id),
            embedding_task_id=int(task.embedding_task_id),
            update_by=user_name,
            user_id=int(user_id),
            item_total=len(snapshot),
            resume=False,
            pending=pending,
        )

    @classmethod
    async def _launch_existing(
        cls,
        run: KnowledgeEvalRun,
        *,
        update_by: str,
        user_id: int,
        message: str,
    ) -> EvalRunLaunchVo:
        saved = await EvalTaskDao.list_run_items(int(run.run_id))
        done_ids = {int(item.dataset_item_id) for item in saved if item.dataset_item_id is not None}
        prior: list[EvalItemScoreVo] = []
        for item in saved:
            try:
                prior.append(EvalItemScoreVo.model_validate(json.loads(item.metrics or '{}')))
            except Exception:
                prior.append(EvalItemScoreVo())
        snapshot = [
            EvalDatasetSnapshotItemVo.model_validate(raw)
            for raw in json.loads(run.dataset_snapshot or '[]')
        ]
        pending = [
            EvalRunPendingQuestionVo(sort_order=idx, snap=item)
            for idx, item in enumerate(snapshot)
            if item.item_id is None or int(item.item_id) not in done_ids
        ]
        return EvalRunLaunchVo(
            run=EvalRunModel(**CamelCaseUtil.transform_result(run)),
            message=message,
            run_id=int(run.run_id),
            embedding_task_id=int(run.embedding_task_id),
            update_by=update_by,
            user_id=user_id,
            item_total=len(snapshot),
            resume=True,
            prior_scores=prior,
            pending=pending,
        )

    @classmethod
    async def _execute_run_bg(cls, launch: EvalRunLaunchVo, lock: DistributedLock) -> None:
        try:
            await cls._execute_run(launch)
        except Exception as e:
            logger.opt(exception=True).error('评测 run 失败 run_id={} err={}', launch.run_id, e)
            await cls._fail_run(launch.run_id, launch.update_by, str(e)[:1900])
        finally:
            await lock.release()

    @classmethod
    @transactional()
    async def _fail_run(cls, run_id: int, update_by: str, error: str) -> None:
        await EvalTaskDao.update_run(
            {
                'run_id': run_id,
                'status': 'FAILED',
                'error_message': error,
                'finished_at': datetime.now(),
                'update_by': update_by,
                'update_time': datetime.now(),
            }
        )

    @classmethod
    async def _execute_run(cls, launch: EvalRunLaunchVo) -> None:
        await cls._mark_running(launch.run_id, launch.update_by, reset_started=not launch.resume)
        # 裁判对话模型走测评集适配，向量模型走文档向量化适配
        chat_config, embedding_config = await EvalDatasetGenerateService._model_configs()
        batch_size = max(1, int(EvalDatasetConfig.eval_run_batch_size))
        total = launch.item_total
        scored: list[EvalItemScoreVo] = list(launch.prior_scores)
        now = datetime.now()
        pending = launch.pending

        unanswered: list[str] = []
        for start in range(0, len(pending), batch_size):
            chunk = pending[start:start + batch_size]
            outcomes = await asyncio.gather(
                *[cls._answer_pending(launch, question, now, chat_config, embedding_config) for question in chunk],
                return_exceptions=True,
            )
            batch_items: list[KnowledgeEvalRunItem] = []
            retry: list[EvalRunPendingQuestionVo] = []
            for question, outcome in zip(chunk, outcomes, strict=True):
                if isinstance(outcome, Exception):
                    logger.opt(exception=outcome).error('评测单题失败，改为单题重试 run_id={}', launch.run_id)
                    retry.append(question)
                    continue
                item, score = outcome
                batch_items.append(item)
                scored.append(score)
            for question in retry:
                try:
                    item, score = await cls._answer_pending(launch, question, now, chat_config, embedding_config)
                except Exception as e:
                    logger.opt(exception=e).error('评测单题重试仍失败 run_id={}', launch.run_id)
                    message = str(e)[:500]
                    unanswered.append(message)
                    item, score = cls._unanswered_item(launch, question, now, message)
                batch_items.append(item)
                scored.append(score)
            batch_items.sort(key=lambda row: row.sort_order or 0)
            summary = cls._aggregate_metrics(scored, item_total=total)
            if batch_items:
                await cls._save_batch(launch.run_id, batch_items, summary, launch.update_by, finished=False)
            logger.info('评测进度 run_id={} {}/{}', launch.run_id, summary.item_done, summary.item_total)

        summary = cls._aggregate_metrics(scored, item_total=total)
        if unanswered:
            summary.note = unanswered[0]
        await cls._save_batch(
            launch.run_id,
            [],
            summary,
            launch.update_by,
            finished=True,
            error_message='；'.join(unanswered)[:1900] or None,
        )

    @classmethod
    @transactional()
    async def _mark_running(cls, run_id: int, update_by: str, *, reset_started: bool = True) -> None:
        values: dict[str, Any] = {
            'run_id': run_id,
            'status': 'RUNNING',
            'update_by': update_by,
            'update_time': datetime.now(),
        }
        if reset_started:
            values['started_at'] = datetime.now()
        await EvalTaskDao.update_run(values)

    @classmethod
    @transactional()
    async def _save_batch(
        cls,
        run_id: int,
        run_items: list[KnowledgeEvalRunItem],
        summary: EvalRunSummaryVo,
        update_by: str,
        *,
        finished: bool,
        error_message: str | None = None,
    ) -> None:
        """一批题入库，并刷新进度和当前均分。全部完成时把执行标成成功。"""
        if run_items:
            await EvalTaskDao.insert_run_items(run_items)
        values: dict[str, Any] = {
            'run_id': run_id,
            'summary_metrics': json.dumps(summary.model_dump(), ensure_ascii=False),
            'report_text': summary.note or '',
            'update_by': update_by,
            'update_time': datetime.now(),
        }
        if finished:
            values['status'] = 'SUCCESS'
            values['finished_at'] = datetime.now()
            values['error_message'] = error_message
        await EvalTaskDao.update_run(values)

    @classmethod
    async def _answer_pending(
        cls,
        launch: EvalRunLaunchVo,
        question: EvalRunPendingQuestionVo,
        now: datetime,
        chat_config: ChatModelConfigModel,
        embedding_config: EmbeddingModelConfigModel,
    ) -> tuple[KnowledgeEvalRunItem, EvalItemScoreVo]:
        return await cls._answer_one(
            run_id=launch.run_id,
            sort_order=question.sort_order,
            snap=question.snap,
            embedding_task_id=launch.embedding_task_id,
            user_id=launch.user_id,
            update_by=launch.update_by,
            now=now,
            chat_config=chat_config,
            embedding_config=embedding_config,
        )

    @classmethod
    def _unanswered_item(
        cls,
        launch: EvalRunLaunchVo,
        question: EvalRunPendingQuestionVo,
        now: datetime,
        message: str,
    ) -> tuple[KnowledgeEvalRunItem, EvalItemScoreVo]:
        """采数重试仍失败时留下空答案，不让这一题挡住后面的题。"""
        snap = question.snap
        score = EvalItemScoreVo(note=message)
        ref = snap.reference_excerpts
        item = KnowledgeEvalRunItem(
            run_id=launch.run_id,
            dataset_item_id=snap.item_id,
            question=snap.question or '',
            ground_truth=snap.ground_truth or '',
            reference_excerpts=ref if isinstance(ref, str) else json.dumps(ref, ensure_ascii=False),
            contexts='[]',
            answer='',
            metrics=json.dumps(score.model_dump(), ensure_ascii=False),
            sort_order=question.sort_order,
            create_by=launch.update_by,
            create_time=now,
            update_by=launch.update_by,
            update_time=now,
            del_flag=DeleteFlag.NORMAL.value,
        )
        return item, score

    @classmethod
    async def _answer_one(
        cls,
        *,
        run_id: int,
        sort_order: int,
        snap: EvalDatasetSnapshotItemVo,
        embedding_task_id: int,
        user_id: int,
        update_by: str,
        now: datetime,
        chat_config: ChatModelConfigModel,
        embedding_config: EmbeddingModelConfigModel,
    ) -> tuple[KnowledgeEvalRunItem, EvalItemScoreVo]:
        question = snap.question or ''
        ground_truth = snap.ground_truth or ''
        ref = snap.reference_excerpts
        try:
            result = await QaEvalService.eval_answer(
                EvalQaAnswerRequestVo(
                    question=question,
                    release_tag='canary',
                    task_id=embedding_task_id,
                    user_id=user_id,
                )
            )
        except Exception as e:
            raise ServiceException(message=f'采数失败 item={snap.item_id}: {e}') from e
        answer = result.answer or ''
        contexts = list(result.contexts or [])
        score = await cls._score_item(
            question=question,
            ground_truth=ground_truth,
            answer=answer,
            contexts=contexts,
            chat_config=chat_config,
            embedding_config=embedding_config,
        )
        item = KnowledgeEvalRunItem(
            run_id=run_id,
            dataset_item_id=snap.item_id,
            question=question,
            ground_truth=ground_truth,
            reference_excerpts=ref if isinstance(ref, str) else json.dumps(ref, ensure_ascii=False),
            contexts=json.dumps(contexts, ensure_ascii=False),
            answer=answer,
            metrics=json.dumps(score.model_dump(), ensure_ascii=False),
            sort_order=sort_order,
            create_by=update_by,
            create_time=now,
            update_by=update_by,
            update_time=now,
            del_flag=DeleteFlag.NORMAL.value,
        )
        return item, score

    @classmethod
    async def _score_item(
        cls,
        *,
        question: str,
        ground_truth: str,
        answer: str,
        contexts: list[str],
        chat_config: ChatModelConfigModel,
        embedding_config: EmbeddingModelConfigModel,
    ) -> EvalItemScoreVo:
        """用测评集适配的对话模型和文档向量模型打四个指标。"""

        def _invoke() -> EvalItemScoreVo:
            # 模型建在 RAGAS 自己的循环里，异步连接才不会绑到服务循环上
            timeout = float(EvalDatasetConfig.eval_metric_timeout_seconds)
            chat = LangChainModelFactory.create_uncached_chat_model(chat_config, timeout=timeout)
            embeddings = LangChainModelFactory.create_embedding_model(embedding_config, timeout=timeout)
            return cls._evaluate_sample(chat, embeddings, question, ground_truth, answer, contexts)

        try:
            return await asyncio.to_thread(_run_on_ragas_loop, _invoke)
        except ServiceException:
            raise
        except Exception as e:
            logger.warning('Ragas 不可用或评分失败，使用占位指标: {}', e)
            return EvalItemScoreVo(note=f'placeholder metrics; ragas unavailable: {e}')

    @classmethod
    def _evaluate_sample(
        cls,
        chat: Any,
        embeddings: Any,
        question: str,
        ground_truth: str,
        answer: str,
        contexts: list[str],
    ) -> EvalItemScoreVo:
        from knowledge_admin.infra.ragas_vertex_compat import ensure_ragas_vertex_chat

        # ragas 加载时会导入已删除的 ChatVertexAI，必须先补上占位模块
        ensure_ragas_vertex_chat()
        from datasets import Dataset

        from knowledge_admin.service.eval_metric_pool import get_metric_suite_pool

        ds = Dataset.from_dict(
            {
                'question': [question],
                'answer': [answer],
                'contexts': [contexts],
                'ground_truth': [ground_truth],
            }
        )
        with get_metric_suite_pool().borrow() as suite:
            return cls._read_metric_row(cls._run_metrics(ds, suite.metrics(), chat, embeddings))

    @classmethod
    def _run_metrics(cls, dataset: Any, metrics: list, chat: Any, embeddings: Any) -> Any:
        from ragas import evaluate
        from ragas.run_config import RunConfig

        timeout = max(1, int(EvalDatasetConfig.eval_metric_timeout_seconds))
        return evaluate(
            dataset,
            metrics=metrics,
            llm=chat,
            embeddings=embeddings,
            run_config=RunConfig(timeout=timeout),
        ).to_pandas().iloc[0]

    @classmethod
    def _read_metric_row(cls, row: Any) -> EvalItemScoreVo:
        return EvalItemScoreVo(
            context_recall=cls._metric_number(row.get('context_recall')),
            context_precision=cls._metric_number(row.get('context_precision')),
            faithfulness=cls._metric_number(row.get('faithfulness')),
            answer_relevancy=cls._metric_number(row.get('answer_relevancy')),
        )

    @classmethod
    def _metric_number(cls, value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if number != number:
            return None
        return number

    @classmethod
    def _aggregate_metrics(cls, scores: list[EvalItemScoreVo], *, item_total: int) -> EvalRunSummaryVo:
        def _avg(name: str) -> float | None:
            vals = [value for score in scores if (value := getattr(score, name)) is not None]
            return (sum(vals) / len(vals)) if vals else None

        notes = [score.note for score in scores if score.note]
        return EvalRunSummaryVo(
            item_total=item_total,
            item_done=len(scores),
            context_recall=_avg('context_recall'),
            context_precision=_avg('context_precision'),
            faithfulness=_avg('faithfulness'),
            answer_relevancy=_avg('answer_relevancy'),
            note=notes[0] if notes else None,
        )

    @classmethod
    async def list_runs(
        cls, query: EvalRunPageQueryModel, is_page: bool = True
    ) -> PageModel | list:
        if not query.eval_task_id:
            raise ServiceException(message='evalTaskId 不能为空')
        return await EvalTaskDao.list_runs(query, is_page=is_page)

    @classmethod
    async def get_report(cls, run_id: int) -> EvalRunReportVo:
        run = await EvalTaskDao.get_run_by_id(run_id)
        if not run:
            raise ServiceException(message='run 不存在')
        items = await EvalTaskDao.list_run_items(run_id)
        summary: dict[str, Any] = {}
        if run.summary_metrics:
            try:
                summary = json.loads(run.summary_metrics)
            except json.JSONDecodeError:
                summary = {'raw': run.summary_metrics}
        return EvalRunReportVo(
            run=EvalRunModel(**CamelCaseUtil.transform_result(run)),
            items=[EvalRunItemModel(**CamelCaseUtil.transform_result(i)) for i in items],
            summary=summary,
        )

    @classmethod
    @transactional()
    async def publish(
        cls,
        eval_task_id: int,
        current_user: CurrentUserModel,
    ) -> CrudResponseModel:
        task = await EvalTaskDao.get_task_by_id(eval_task_id)
        if not task:
            raise ServiceException(message='测评任务不存在')
        cls._ensure_open(task)
        success_count = await EvalTaskDao.count_success_runs(eval_task_id)
        if success_count < 1:
            raise ServiceException(message='需至少一次 SUCCESS run 后方可发布')

        await EmbeddingService.promote(PromoteTaskRequest(embedding_task_id=int(task.embedding_task_id)))
        now = datetime.now()
        await EvalTaskDao.update_task(
            {
                'eval_task_id': eval_task_id,
                'status': 'ARCHIVED',
                'publish_time': now,
                'update_by': current_user.user.user_name or '',
                'update_time': now,
            }
        )
        return CrudResponseModel(is_success=True, message='发布成功，任务已归档')
