"""
测评集生成：先在本地圈资料，再出题。

简单题、多跳题各走一次 RAGAS，模糊、对抗、综合题再自己写一次。
不超过 20 页和超过 20 页都是这四步，区别只在圈资料选哪些页。
每步成功都落库。重试从第一个没完成的阶段接着跑。
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.config.env import (
    AiModelFunctionAdapterConfig,
    EmbeddingConfig,
    EvalDatasetConfig,
    SemaphoreConfig,
)
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.redis import DistributedSemaphore, SemaphoreKey
from knowledge_common.service.document_embedding_service import DocumentEmbeddingService
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.langchain_model_vo import ChatModelConfigModel, EmbeddingModelConfigModel
from langchain_core.documents import Document

from knowledge_admin.enums.eval_dataset_status_enum import (
    RUNNABLE_STATUSES,
    EvalDatasetStatus,
    failed_stage,
    pending_stage,
    stage_finished,
)
from knowledge_admin.infra.minio.minio_service import KnowledgeMinioService
from knowledge_admin.infra.rpc.content.service.document_section_service import (
    DocumentSectionService as ContentDocumentSectionService,
)
from knowledge_admin.infra.rpc.content.service.source_file_service import SourceFileService
from knowledge_admin.service.eval_custom_question_service import EvalCustomQuestionService
from knowledge_admin.service.eval_dataset_service import EvalDatasetService
from knowledge_admin.service.eval_question_plan import plan_from_pages, plan_from_sections, plan_has_material
from knowledge_admin.vo.eval_question_plan_vo import (
    EvalDatasetMaterialRecordVo,
    EvalMaterialDocVo,
    EvalPageVo,
    GenerationMaterialPlanVo,
    RagasCallVo,
)
from knowledge_admin.vo.eval_vo import GeneratedDatasetItemVo

if TYPE_CHECKING:
    from collections.abc import Callable

    from knowledge_common.facade.api.knowledge_content.source_file_vo import SourceMarkdownFileVo

    from knowledge_admin.mapper.do.eval_do import KnowledgeEvalDataset

_DIFFICULTY_MAX = 64
_RAGAS_MAX_WORKERS = 16
_cleanup_tasks: set[asyncio.Task[None]] = set()
_generate_semaphore: DistributedSemaphore | None = None


async def get_eval_dataset_generate_semaphore() -> DistributedSemaphore:
    """懒初始化生成信号量。多 worker 下 create_pool 只生效一次。"""
    global _generate_semaphore  # noqa: PLW0603
    if _generate_semaphore is None:
        key = SemaphoreKey.eval_dataset_generate_key()
        await DistributedSemaphore.create_pool(
            key=key,
            size=SemaphoreConfig.semaphore_eval_dataset_generate_size,
        )
        _generate_semaphore = DistributedSemaphore(key=key)
    return _generate_semaphore


class EvalDatasetGenerateService:
    """圈资料后出题，题目写回测评集。"""

    @classmethod
    async def run(cls, dataset_id: int) -> None:
        dataset = await EvalDatasetService.load_generating(dataset_id)
        if dataset is None:
            logger.warning('[EvalDatasetGenerate] 测评集不存在 dataset_id={}', dataset_id)
            return
        if dataset.status not in RUNNABLE_STATUSES:
            logger.info(
                '[EvalDatasetGenerate] 测评集不在出题进度中，跳过 dataset_id={} status={}',
                dataset_id,
                dataset.status,
            )
            return
        update_by = dataset.update_by or ''
        stage = '' if dataset.status == EvalDatasetStatus.INIT.value else dataset.status
        stage_name = pending_stage(stage) or 'CUSTOM'
        try:
            # 续上出题中，避免这轮还在出题时被当成卡住重新出题
            await EvalDatasetService.touch_generating(dataset_id, update_by)
            if not stage_finished(stage, 'MATERIAL') or _saved_material(dataset.material_plan) is None:
                stage_name = 'MATERIAL'
            record, stage = await cls._ensure_material(dataset, stage, update_by)
            if record is None:
                return
            plan = record.plan
            chat_config: ChatModelConfigModel | None = None
            embedding_config: EmbeddingModelConfigModel | None = None
            if not stage_finished(stage, 'SIMPLE'):
                stage_name = 'SIMPLE'
                chat_config, embedding_config = await cls._model_configs()
                items = await cls._ragas_items(
                    chat_config,
                    embedding_config,
                    RagasCallVo(docs=plan.simple_docs, testset_size=plan.quota.simple, kind='single'),
                )
                await EvalDatasetService.append_stage_items(
                    dataset_id, items, EvalDatasetStatus.SIMPLE_DONE, update_by, finish=False
                )
                stage = EvalDatasetStatus.SIMPLE_DONE.value
                logger.info('[EvalDatasetGenerate] 简单题完成 dataset_id={} saved={}', dataset_id, len(items))
            if not stage_finished(stage, 'MULTI'):
                stage_name = 'MULTI'
                if chat_config is None or embedding_config is None:
                    chat_config, embedding_config = await cls._model_configs()
                items = await cls._ragas_items(
                    chat_config,
                    embedding_config,
                    RagasCallVo(docs=plan.multi_hop_docs, testset_size=plan.quota.multi_hop, kind='multi'),
                )
                await EvalDatasetService.append_stage_items(
                    dataset_id, items, EvalDatasetStatus.MULTI_DONE, update_by, finish=False
                )
                stage = EvalDatasetStatus.MULTI_DONE.value
                logger.info('[EvalDatasetGenerate] 多跳题完成 dataset_id={} saved={}', dataset_id, len(items))
            if not stage_finished(stage, 'CUSTOM'):
                stage_name = 'CUSTOM'
                if chat_config is None:
                    chat_config = await cls._chat_config()
                chat = LangChainModelFactory.get_base_chat_model(chat_config)
                items = await EvalCustomQuestionService.generate(chat, plan.custom_docs, plan.quota)
                saved = await EvalDatasetService.append_stage_items(
                    dataset_id, items, EvalDatasetStatus.CUSTOM_DONE, update_by, finish=True
                )
                if saved <= 0:
                    logger.info('[EvalDatasetGenerate] 未生成题目 dataset_id={}', dataset_id)
                    return
                _schedule_cache_cleanup(dataset_id, record.cached_object_keys)
                logger.info(
                    '[EvalDatasetGenerate] 完成 dataset_id={} requested={} saved={}',
                    dataset_id,
                    dataset.question_count,
                    saved,
                )
        except Exception as exc:
            logger.opt(exception=True).error(
                '[EvalDatasetGenerate] 失败 dataset_id={} stage={} err={}', dataset_id, stage_name, exc
            )
            await EvalDatasetService.mark_stage_failed(
                dataset_id, failed_stage(stage_name).value, str(exc)[:480], update_by
            )

    @classmethod
    async def _ensure_material(
        cls, dataset: KnowledgeEvalDataset, stage: str, update_by: str
    ) -> tuple[EvalDatasetMaterialRecordVo | None, str]:
        """圈资料已完成就读库。否则下载并抽样，成功后写入测评集。"""
        dataset_id = int(dataset.dataset_id)
        record = _saved_material(dataset.material_plan)
        if stage_finished(stage, 'MATERIAL') and record is not None:
            logger.info('[EvalDatasetGenerate] 圈资料已完成，跳过 dataset_id={}', dataset_id)
            return record, stage
        if int(dataset.item_count or 0) > 0:
            await EvalDatasetService.clear_generated_items(dataset_id, update_by)
        plan, cached_keys = await cls._load_plan(int(dataset.doc_id), int(dataset.question_count))
        if not plan_has_material(plan):
            await EvalDatasetService.mark_stage_failed(
                dataset_id, EvalDatasetStatus.MATERIAL_FAILED.value, '文档没有可出题的原文', update_by
            )
            return None, EvalDatasetStatus.MATERIAL_FAILED.value
        record = EvalDatasetMaterialRecordVo(plan=plan, cached_object_keys=cached_keys)
        await EvalDatasetService.save_material(dataset_id, record, update_by)
        cls._log_plan(dataset_id, plan)
        return record, EvalDatasetStatus.MATERIAL_DONE.value

    @classmethod
    async def _model_configs(cls) -> tuple[ChatModelConfigModel, EmbeddingModelConfigModel]:
        return await cls._chat_config(), await cls._embedding_config()

    @classmethod
    async def _load_plan(cls, doc_id: int, question_count: int) -> tuple[GenerationMaterialPlanVo, list[str]]:
        listing = await SourceFileService.list_source_files(doc_id)
        files = listing.files
        if not files:
            return plan_from_pages([], question_count), []
        # 带网页地址的是爬取，一页一个文件。否则是上传，交给 content 切节
        if any((row.source_url or '').strip() for row in files):
            pages = await cls._download_pages(files)
            keys = [row.doc_key for row in files if row.doc_key]
            return plan_from_pages(pages, question_count), keys
        sections = await ContentDocumentSectionService.list_sections(doc_id)
        return plan_from_sections(sections.sections, question_count), []

    @classmethod
    async def _download_pages(cls, files: list[SourceMarkdownFileVo]) -> list[EvalPageVo]:
        sem = asyncio.Semaphore(EvalDatasetConfig.eval_dataset_fetch_concurrency)

        async def _load(order: int, row: SourceMarkdownFileVo) -> tuple[int, EvalPageVo | None]:
            async with sem:
                text = (await KnowledgeMinioService.download_content(row.doc_key)).strip()
            if not text:
                return order, None
            return order, EvalPageVo(
                index=order,
                source_url=row.source_url or '',
                text=text,
                file_id=row.file_id,
                doc_name=row.doc_name or '',
            )

        loaded = await asyncio.gather(*[_load(order, row) for order, row in enumerate(files)])
        loaded.sort(key=lambda item: item[0])
        return [page for _, page in loaded if page is not None]

    @classmethod
    async def _ragas_items(
        cls,
        chat_config: ChatModelConfigModel,
        embedding_config: EmbeddingModelConfigModel,
        call: RagasCallVo,
    ) -> list[GeneratedDatasetItemVo]:
        documents = _langchain_docs(call.docs)
        if call.testset_size <= 0 or not documents:
            return []

        def _invoke() -> Any:
            timeout = float(EvalDatasetConfig.eval_metric_timeout_seconds)
            chat = LangChainModelFactory.create_uncached_chat_model(chat_config, timeout=timeout)
            embeddings = LangChainModelFactory.create_embedding_model(embedding_config, timeout=timeout)
            return cls._call_ragas(chat, embeddings, documents, call)

        try:
            testset = await asyncio.to_thread(_run_on_ragas_loop, _invoke)
        except Exception as exc:
            if call.kind == 'multi' and _is_missing_relationship(exc):
                logger.warning('[EvalDatasetGenerate] 多跳材料建不出关系，这批记 0 道: {}', exc)
                return []
            raise
        return cls._to_items(testset)

    @staticmethod
    def _call_ragas(
        chat: Any,
        embeddings: Any,
        docs: list[Document],
        call: RagasCallVo,
    ) -> Any:
        from knowledge_admin.infra.ragas_vertex_compat import ensure_ragas_vertex_chat  # noqa: PLC0415

        ensure_ragas_vertex_chat()
        # RAGAS 导入会碰 Vertex 占位，必须在 ensure 之后，不能挪到文件头
        from ragas.embeddings import LangchainEmbeddingsWrapper  # noqa: PLC0415
        from ragas.llms import LangchainLLMWrapper  # noqa: PLC0415
        from ragas.run_config import RunConfig  # noqa: PLC0415
        from ragas.testset import TestsetGenerator  # noqa: PLC0415

        # 合成器自带英文指令和英文示例，先改成简体中文再出题
        _require_chinese_query_prompts()
        llm = LangchainLLMWrapper(chat)
        generator = TestsetGenerator(
            llm=llm,
            embedding_model=LangchainEmbeddingsWrapper(embeddings),
            llm_context=_CHINESE_QUERY_RULE,
        )
        return generator.generate_with_langchain_docs(
            docs,
            testset_size=call.testset_size,
            query_distribution=_query_distribution(llm, call.kind),
            run_config=RunConfig(max_workers=_RAGAS_MAX_WORKERS),
        )

    @classmethod
    async def _chat_config(cls) -> ChatModelConfigModel:
        param_id = AiModelFunctionAdapterConfig.eval_dataset_param_id
        adapter = await AiModelFunctionAdapterDao.get_adapter_by_param_id(param_id)
        if adapter is None or not adapter.model_code or not adapter.provider:
            raise ServiceException(message='未配置测评集模型')
        return ChatModelConfigModel(
            model_code=adapter.model_code,
            provider=adapter.provider,
            api_key=adapter.api_key or '',
            base_url=adapter.base_url or '',
            temperature=adapter.temperature if adapter.temperature is not None else 0.3,
            max_tokens=adapter.max_tokens,
        )

    @classmethod
    async def _embedding_config(cls) -> EmbeddingModelConfigModel:
        adapter = await DocumentEmbeddingService.load_adapter()
        return EmbeddingModelConfigModel(
            model_code=adapter.model_code,
            provider=adapter.provider,
            api_key=adapter.api_key or '',
            base_url=adapter.base_url or '',
            dimensions=adapter.dimensions,
            chunk_size=EmbeddingConfig.embedding_api_chunk_size,
            check_embedding_ctx_length=EmbeddingConfig.embedding_check_ctx_length,
        )

    @classmethod
    def _to_items(cls, testset: Any) -> list[GeneratedDatasetItemVo]:
        items: list[GeneratedDatasetItemVo] = []
        for sample in cls._iter_samples(testset):
            question, answer, contexts, name = cls._sample_fields(sample)
            question = question.strip()
            if not question:
                continue
            excerpts = [str(ctx).strip() for ctx in contexts if str(ctx).strip()]
            items.append(
                GeneratedDatasetItemVo(
                    question=question,
                    ground_truth=answer.strip(),
                    difficulty=_question_type(name),
                    reference_excerpts=excerpts,
                    used_chunk_ids=[],
                    keypoints=[],
                )
            )
        return items

    @staticmethod
    def _iter_samples(testset: Any) -> list[Any]:
        samples = getattr(testset, 'samples', None)
        if samples:
            return list(samples)
        to_pandas = getattr(testset, 'to_pandas', None)
        if to_pandas is None:
            return []
        frame = to_pandas()
        return list(frame.to_dict(orient='records'))

    @staticmethod
    def _sample_fields(sample: Any) -> tuple[str, str, list[Any], str]:
        if isinstance(sample, dict):
            contexts = sample.get('reference_contexts') or []
            return (
                str(sample.get('user_input') or sample.get('question') or ''),
                str(sample.get('reference') or sample.get('ground_truth') or ''),
                list(contexts),
                str(sample.get('synthesizer_name') or ''),
            )
        ev = getattr(sample, 'eval_sample', None) or sample
        contexts = getattr(ev, 'reference_contexts', None) or []
        return (
            str(getattr(ev, 'user_input', None) or getattr(ev, 'question', None) or ''),
            str(getattr(ev, 'reference', None) or ''),
            list(contexts),
            str(getattr(sample, 'synthesizer_name', None) or ''),
        )

    @staticmethod
    def _log_plan(dataset_id: int, plan: GenerationMaterialPlanVo) -> None:
        quota = plan.quota
        logger.info(
            '[EvalDatasetGenerate] 圈资料 dataset_id={} separate={} simple_docs={} multi_docs={} '
            'quota={}/{}/{}/{}/{}',
            dataset_id,
            plan.separate_ragas_calls,
            len(plan.simple_docs),
            len(plan.multi_hop_docs),
            quota.simple,
            quota.multi_hop,
            quota.comprehensive,
            quota.vague,
            quota.adversarial,
        )


def _langchain_docs(docs: list[EvalMaterialDocVo]) -> list[Document]:
    converted: list[Document] = []
    for doc in docs:
        text = doc.page_content.strip()
        if not text:
            continue
        converted.append(
            Document(
                page_content=text,
                metadata={
                    'file_id': doc.file_id or 0,
                    'doc_name': doc.doc_name,
                    'source_url': doc.source_url,
                    'title': doc.title,
                },
            )
        )
    return converted


def _schedule_cache_cleanup(dataset_id: int, object_names: list[str]) -> None:
    if not object_names:
        return
    task = asyncio.create_task(_cleanup_cached_files(dataset_id, object_names))
    _cleanup_tasks.add(task)
    task.add_done_callback(_cleanup_tasks.discard)


async def _cleanup_cached_files(dataset_id: int, object_names: list[str]) -> None:
    try:
        removed = await KnowledgeMinioService.delete_cached_files(object_names)
        logger.info('[EvalDatasetGenerate] 已清理本地下载 dataset_id={} removed={}', dataset_id, removed)
    except Exception:
        logger.opt(exception=True).error('[EvalDatasetGenerate] 清理本地下载失败 dataset_id={}', dataset_id)


def _run_on_ragas_loop(fn: Callable[[], Any]) -> Any:
    """RAGAS 抽实体、出题各调一次 asyncio.run，默认跑完就关掉循环。

    模型的异步连接绑在第一次的循环上，下一次关连接会报 Event loop is closed。
    这个线程先装一个不关闭的循环，后面的 asyncio.run 都复用它。
    """
    import nest_asyncio  # noqa: PLC0415

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    nest_asyncio.apply(loop)
    try:
        return fn()
    finally:
        if not loop.is_closed():
            loop.close()
        asyncio.set_event_loop(None)


def _question_type(synthesizer_name: str) -> str:
    """RAGAS 合成器名收成题目类型。单跳是简单题，两种多跳都是多跳题。"""
    name = synthesizer_name.strip()
    if 'single_hop' in name:
        return 'simple'
    if 'multi_hop' in name:
        return 'multi_hop'
    return name[:_DIFFICULTY_MAX]


_CHINESE_QUERY_RULE = (
    '问句和标准答案必须使用简体中文。'
    '人称、主题或材料里出现英文时，问句和答案仍然用简体中文，专有名词可以保留原文。'
    'style 为 Misspelled queries 或 Poor grammar 时，用中文口语或中文错字，不要改成英文。'
    '标准答案必须直接写出材料里的事实，读答案就能对上问题。'
    '不要把网址、文档名、章节名或「详见某文档」当作答案，也不要让人自己去链接里找。'
    '材料里如果只有链接或书名，没有把事情本身写出来，就不要就这个点出题。'
)
_CHINESE_PERSONA_RULE = '姓名和职责描述必须使用简体中文。'
_CHINESE_MARK = '必须使用简体中文'


def _require_chinese_query_prompts() -> None:
    """RAGAS 出题提示词默认是英文，示例也是英文问句。改类属性后，后面新建的合成器都会用中文。"""
    from ragas.prompt import StringIO  # noqa: PLC0415
    from ragas.testset import persona as persona_prompts  # noqa: PLC0415
    from ragas.testset.synthesizers.multi_hop import prompts as multi_hop_prompts  # noqa: PLC0415
    from ragas.testset.synthesizers.single_hop import prompts as single_hop_prompts  # noqa: PLC0415

    _patch_prompt(
        single_hop_prompts.QueryAnswerGenerationPrompt,
        [
            (
                single_hop_prompts.QueryCondition(
                    persona=persona_prompts.Persona(name='运维工程师', role_description='关注安装和部署步骤。'),
                    term='年假',
                    query_style='Perfect grammar',
                    query_length='medium',
                    context='员工入职满一年后，每年享有 10 天带薪年假。年假须提前 3 个工作日申请。',
                    llm_context=_CHINESE_QUERY_RULE,
                ),
                single_hop_prompts.GeneratedQueryAnswer(
                    query='带薪年假有多少天，申请要提前多久？',
                    answer='入职满一年后每年享有 10 天带薪年假，须提前 3 个工作日申请。',
                ),
            ),
            (
                single_hop_prompts.QueryCondition(
                    persona=persona_prompts.Persona(name='应用开发者', role_description='关心向量库在智能体里的用途。'),
                    term='向量检索',
                    query_style='Perfect grammar',
                    query_length='medium',
                    context=(
                        'Milvus 为 AI Agent 提供向量检索，用来保存和查找向量。'
                        '详细介绍见 https://milvus.io/docs/zh/milvus_for_agents.md。'
                    ),
                    llm_context=_CHINESE_QUERY_RULE,
                ),
                single_hop_prompts.GeneratedQueryAnswer(
                    query='Milvus 在 AI Agent 里做什么？',
                    answer='Milvus 为 AI Agent 提供向量检索，用来保存和查找向量。',
                ),
            ),
        ],
    )
    _patch_prompt(
        multi_hop_prompts.QueryAnswerGenerationPrompt,
        [
            (
                multi_hop_prompts.QueryConditions(
                    persona=persona_prompts.Persona(name='人事专员', role_description='负责假期审批。'),
                    themes=['年假审批', '病假审批'],
                    query_style='Perfect grammar',
                    query_length='medium',
                    context=[
                        '<1-hop> 年假须提前 3 个工作日申请，由直属主管审批。',
                        '<2-hop> 病假 3 天以内由直属主管审批，超过 3 天须部门负责人审批。',
                    ],
                    llm_context=_CHINESE_QUERY_RULE,
                ),
                multi_hop_prompts.GeneratedQueryAnswer(
                    query='年假和病假分别由谁审批？',
                    answer='年假由直属主管审批。病假 3 天以内由直属主管审批，超过 3 天须部门负责人审批。',
                ),
            )
        ],
    )
    _patch_prompt(
        persona_prompts.PersonaGenerationPrompt,
        [
            (
                StringIO(text='年假须提前 3 个工作日申请，由直属主管审批。'),
                persona_prompts.Persona(name='人事专员', role_description='负责员工假期申请和审批。'),
            )
        ],
        _CHINESE_PERSONA_RULE,
    )


def _patch_prompt(prompt_cls: type, examples: list[tuple[Any, Any]], rule: str = _CHINESE_QUERY_RULE) -> None:
    if _CHINESE_MARK in prompt_cls.instruction:
        return
    prompt_cls.instruction = f'{prompt_cls.instruction}\n\n### 要求\n{rule}'
    prompt_cls.examples = examples


def _saved_material(raw: str | None) -> EvalDatasetMaterialRecordVo | None:
    text = (raw or '').strip()
    if not text:
        return None
    try:
        record = EvalDatasetMaterialRecordVo.model_validate_json(text)
    except ValueError:
        logger.warning('[EvalDatasetGenerate] 圈资料结果无法读取，重新圈资料')
        return None
    if not plan_has_material(record.plan):
        return None
    return record


def _query_distribution(llm: Any, kind: str) -> list[tuple[Any, float]]:
    """简单题只用单跳合成器，多跳题只用两种多跳合成器。"""
    from ragas.testset.synthesizers.multi_hop.abstract import (  # noqa: PLC0415
        MultiHopAbstractQuerySynthesizer,
    )
    from ragas.testset.synthesizers.multi_hop.specific import (  # noqa: PLC0415
        MultiHopSpecificQuerySynthesizer,
    )
    from ragas.testset.synthesizers.single_hop.specific import (  # noqa: PLC0415
        SingleHopSpecificQuerySynthesizer,
    )

    if kind == 'single':
        return [(SingleHopSpecificQuerySynthesizer(llm=llm, llm_context=_CHINESE_QUERY_RULE), 1.0)]
    return [
        (MultiHopSpecificQuerySynthesizer(llm=llm, llm_context=_CHINESE_QUERY_RULE), 0.5),
        (MultiHopAbstractQuerySynthesizer(llm=llm, llm_context=_CHINESE_QUERY_RULE), 0.5),
    ]


def _is_missing_relationship(exc: Exception) -> bool:
    message = str(exc)
    return 'No clusters' in message or 'No compatible query' in message
