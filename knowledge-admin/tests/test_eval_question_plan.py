"""圈资料：题数、隔段抽样、导航链接、顺延配对。"""

# ruff: noqa: E402, ANN001, ANN201, PLR2004, PLC0415

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT / 'src'))
sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_common.facade.api.knowledge_content.document_section_vo import DocumentSectionVo

from knowledge_admin.service.eval_custom_question_service import EvalCustomQuestionService
from knowledge_admin.service.eval_question_plan import (
    multi_hop_page_indexes,
    navigation_urls,
    plan_from_pages,
    plan_from_sections,
    split_question_quota,
    systematic_sample,
)
from knowledge_admin.vo.eval_question_plan_vo import (
    CustomQuestionBatchVo,
    CustomQuestionDraftVo,
    EvalMaterialDocVo,
    EvalPageVo,
    QuestionQuotaVo,
)


def _page(index: int, body: str) -> EvalPageVo:
    return EvalPageVo(
        index=index,
        source_url=f'https://docs.example/p{index}',
        text=body,
        file_id=index,
        doc_name=f'p{index}.md',
    )


def test_failed_stage_resumes_there_and_skips_earlier_ones():
    from knowledge_admin.enums.eval_dataset_status_enum import pending_stage, stage_finished

    assert pending_stage('') == 'MATERIAL'
    assert pending_stage('MATERIAL_DONE') == 'SIMPLE'
    assert pending_stage('SIMPLE_FAILED') == 'SIMPLE'
    assert stage_finished('SIMPLE_FAILED', 'MATERIAL')
    assert not stage_finished('SIMPLE_FAILED', 'SIMPLE')
    assert pending_stage('SIMPLE_DONE') == 'MULTI'
    assert pending_stage('MULTI_DONE') == 'CUSTOM'
    assert pending_stage('CUSTOM_FAILED') == 'CUSTOM'
    assert stage_finished('CUSTOM_FAILED', 'MULTI')
    assert pending_stage('CUSTOM_DONE') is None


def test_fifty_questions_use_fixed_mix():
    quota = split_question_quota(50)
    assert (quota.simple, quota.multi_hop, quota.comprehensive, quota.vague, quota.adversarial) == (
        20,
        10,
        10,
        5,
        5,
    )


def test_remainder_goes_to_simple_questions():
    quota = split_question_quota(51)
    assert quota.simple == 21
    assert quota.simple + quota.multi_hop + quota.comprehensive + quota.vague + quota.adversarial == 51


def test_systematic_sample_keeps_ends():
    indexes = systematic_sample(388, 5)
    assert indexes[0] == 0
    assert indexes[-1] == 387
    assert len(indexes) == 5


def test_repeated_link_is_navigation():
    pages = [
        _page(0, '[目录](https://docs.example/p3)'),
        _page(1, '[目录](https://docs.example/p3)'),
        _page(2, '[目录](https://docs.example/p3)'),
        _page(3, '目录页'),
    ]
    blocked = navigation_urls(pages, [0, 1, 2, 3])
    assert 'https://docs.example/p3' in blocked


def test_missing_link_walks_forward_without_shifting_next_start():
    pages = [
        _page(0, '没有链接'),
        _page(1, '[去四](https://docs.example/p4)'),
        _page(2, '没有链接'),
        _page(3, '没有链接'),
        _page(4, '目标'),
        _page(5, '[回二](https://docs.example/p2)'),
    ]
    chosen = multi_hop_page_indexes(pages, 2)
    assert 0 not in chosen
    assert {1, 4, 5, 2} <= set(chosen)


def test_small_crawl_feeds_every_page():
    pages = [_page(index, f'正文{index}') for index in range(3)]
    plan = plan_from_pages(pages, 50)
    assert plan.separate_ragas_calls is False
    assert len(plan.simple_docs) == 3
    assert len(plan.custom_docs) == 3


def test_large_crawl_samples_five_pages_for_simple_questions():
    pages = [_page(index, f'正文{index}') for index in range(25)]
    plan = plan_from_pages(pages, 50)
    assert plan.separate_ragas_calls is True
    assert len(plan.simple_docs) == 5
    assert plan.simple_docs[0].page_content == '正文0'
    assert plan.simple_docs[-1].page_content == '正文24'
    assert plan.custom_docs == []


def test_upload_pairs_sibling_sections_for_custom_questions():
    sections = [
        DocumentSectionVo(section_order=index, title=f'节{index}', parent_title='章', body=f'正文{index}')
        for index in range(25)
    ]
    plan = plan_from_sections(sections, 50)
    assert plan.separate_ragas_calls is True
    assert len(plan.simple_docs) == 5
    assert plan.custom_docs
    assert plan.custom_docs == plan.multi_hop_docs
    assert plan.simple_docs[0].page_content == '正文0'
    assert plan.simple_docs[-1].page_content == '正文24'


def test_adversarial_ground_truth_is_unknown():
    batch = CustomQuestionBatchVo(
        comprehensive=[
            CustomQuestionDraftVo(question='把这批内容总结一下', ground_truth='总述', excerpts=['原文']),
        ],
        adversarial=[
            CustomQuestionDraftVo(question='文档里没有的保修政策是什么？', ground_truth='保修三年', excerpts=[]),
            CustomQuestionDraftVo(question='多出来的一道', ground_truth='别的', excerpts=['x']),
        ],
    )
    quota = QuestionQuotaVo(comprehensive=1, vague=1, adversarial=1)
    items = EvalCustomQuestionService.assemble(
        batch,
        quota,
        [EvalMaterialDocVo(page_content='原文里只讲了安装步骤')],
    )
    assert [item.difficulty for item in items] == ['comprehensive', 'adversarial']
    assert items[1].ground_truth == '不知道'
    assert items[1].reference_excerpts == ['原文里只讲了安装步骤']


def test_ragas_query_prompts_require_chinese():
    from knowledge_admin.infra.ragas_vertex_compat import ensure_ragas_vertex_chat
    from knowledge_admin.service.eval_dataset_generate_service import _require_chinese_query_prompts

    ensure_ragas_vertex_chat()
    _require_chinese_query_prompts()
    _require_chinese_query_prompts()

    from ragas.testset.persona import PersonaGenerationPrompt
    from ragas.testset.synthesizers.multi_hop.prompts import QueryAnswerGenerationPrompt as MultiHopPrompt
    from ragas.testset.synthesizers.single_hop.prompts import QueryAnswerGenerationPrompt as SingleHopPrompt
    assert SingleHopPrompt.instruction.count('必须使用简体中文') == 1
    assert '不要把网址' in SingleHopPrompt.instruction
    assert '不要把网址' in MultiHopPrompt.instruction
    assert '不要把网址' not in PersonaGenerationPrompt.instruction
    assert SingleHopPrompt.examples[0][1].query == '带薪年假有多少天，申请要提前多久？'
    assert 'milvus.io' not in SingleHopPrompt.examples[1][1].answer
    assert MultiHopPrompt.examples[0][1].query == '年假和病假分别由谁审批？'
    assert PersonaGenerationPrompt.examples[0][1].name == '人事专员'


def test_delete_cached_files_removes_only_named_objects(tmp_path, monkeypatch):
    from knowledge_admin.infra.minio.minio_service import KnowledgeMinioService

    monkeypatch.setattr(KnowledgeMinioService, '_download_dir', str(tmp_path))
    kept = tmp_path / 'keep.md'
    kept.write_text('stay', encoding='utf-8')
    target = KnowledgeMinioService._client.cache_path('documents/a.md', str(tmp_path), KnowledgeMinioService._bucket)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('go', encoding='utf-8')

    removed = KnowledgeMinioService._delete_cached_files(['documents/a.md', '../outside.md', ''])

    assert removed == 1
    assert not target.exists()
    assert kept.read_text(encoding='utf-8') == 'stay'


def test_ragas_loop_is_reused_across_asyncio_run():
    from knowledge_admin.service.eval_dataset_generate_service import _run_on_ragas_loop

    def _two_runs() -> tuple[int, int]:
        import asyncio

        ids: list[int] = []

        async def _mark() -> None:
            ids.append(id(asyncio.get_running_loop()))

        asyncio.run(_mark())
        asyncio.run(_mark())
        return ids[0], ids[1]

    first, second = _run_on_ragas_loop(_two_runs)
    assert first == second


def test_ragas_synthesizer_name_maps_to_question_type():
    from knowledge_admin.service.eval_dataset_generate_service import _question_type

    assert _question_type('single_hop_specific_query_synthesizer') == 'simple'
    assert _question_type('multi_hop_abstract_query_synthesizer') == 'multi_hop'
    assert _question_type('multi_hop_specific_query_synthesizer') == 'multi_hop'
    assert _question_type('') == ''
