"""filter_chain / seed scope 门禁单元测试"""

from knowledge_content.agents.utils.filter_chain_util import (
    compute_pages_to_remove,
    evaluate_seed_scope,
    extract_filter_chain,
    suggest_seed_from_include_patterns,
    url_matches_filter_chain,
    url_matches_include_pattern,
)
from knowledge_content.service.trial_quality_gate_service import TrialQualityGateService


def test_include_pattern():
    fc = {'include_patterns': ['https://example.com/docs/*'], 'exclude_patterns': []}
    assert url_matches_filter_chain('https://example.com/docs/guide', fc)
    assert not url_matches_filter_chain('https://example.com/blog/post', fc)


def test_include_directory_root_equivalence():
    pattern = 'https://milvus.io/docs/zh/*'
    assert url_matches_include_pattern('https://milvus.io/docs/zh/', pattern)
    assert url_matches_include_pattern('https://milvus.io/docs/zh', pattern)
    assert url_matches_include_pattern('https://milvus.io/docs/zh/quickstart.md', pattern)
    assert not url_matches_include_pattern('https://milvus.io/zh', pattern)


def test_exclude_pattern():
    fc = {'include_patterns': [], 'exclude_patterns': ['*/admin/*']}
    assert url_matches_filter_chain('https://example.com/docs/page', fc)
    assert not url_matches_filter_chain('https://example.com/admin/users', fc)


def test_compute_pages_to_remove():
    crawled = [
        {'url': 'https://example.com/docs/a', 'title': 'A', 'status': 'SUCCESS'},
        {'url': 'https://example.com/blog/b', 'title': 'B', 'status': 'SUCCESS'},
        {'url': 'https://example.com/docs/c', 'title': 'C', 'status': 'FAILED'},
    ]
    fc = {'include_patterns': ['https://example.com/docs/*'], 'exclude_patterns': []}
    removed = compute_pages_to_remove(crawled, fc)
    assert len(removed) == 1
    assert removed[0]['url'] == 'https://example.com/blog/b'


def test_suggest_seed_from_include_patterns():
    seeds = suggest_seed_from_include_patterns([
        'https://milvus.io/docs/zh/*',
        'https://milvus.io/zh/blog/*',
    ])
    assert seeds == [
        'https://milvus.io/docs/zh/',
        'https://milvus.io/zh/blog/',
    ]


def _milvus_config() -> dict:
    return {
        'crawler_run_config': {
            'deep_crawl_strategy': {
                'crawl_strategy': 'BFSDeepCrawlStrategy',
                'max_depth': 3,
                'max_pages': 500,
                'filter_chain': {
                    'include_patterns': [
                        'https://milvus.io/docs/zh/*',
                        'https://milvus.io/zh/blog/*',
                    ],
                    'exclude_patterns': [],
                },
            },
        },
    }


def test_evaluate_seed_scope_mismatch_for_marketing_home():
    scope = evaluate_seed_scope('https://milvus.io/zh', _milvus_config())
    assert scope['applicable'] is True
    assert scope['seed_in_scope'] is False
    assert scope['expansion_ok'] is False
    assert 'SEED_SCOPE_MISMATCH' in scope['issues']
    assert 'https://milvus.io/docs/zh/' in scope['suggested_seed_urls']


def test_evaluate_seed_scope_ok_for_docs_entry():
    scope = evaluate_seed_scope('https://milvus.io/docs/zh/', _milvus_config())
    assert scope['seed_in_scope'] is True
    assert scope['expansion_ok'] is True


def test_evaluate_seed_scope_hub_allowed_when_trial_expanded():
    """枢纽页起步但试爬已扩到 ≥2 个范围内页 → 放行"""
    scope = evaluate_seed_scope(
        'https://milvus.io/zh',
        _milvus_config(),
        pages_yielded=3,
        pages_in_scope=2,
        outbound_in_scope_count=2,
    )
    assert scope['seed_in_scope'] is False
    assert scope['expansion_ok'] is True


def test_no_in_scope_expansion_when_seed_in_scope_but_no_outbound():
    scope = evaluate_seed_scope(
        'https://milvus.io/docs/zh/',
        _milvus_config(),
        pages_yielded=1,
        pages_in_scope=1,
        outbound_in_scope_count=0,
    )
    assert 'NO_IN_SCOPE_EXPANSION' in scope['issues']
    assert scope['expansion_ok'] is False


def test_leaf_document_skips_no_in_scope_expansion():
    """失败修复对 .md 叶页试爬：出链为 0 不触发 NO_IN_SCOPE_EXPANSION"""
    from knowledge_content.agents.utils.filter_chain_util import looks_like_leaf_document_url

    assert looks_like_leaf_document_url('https://milvus.io/docs/zh/milvus-webui.md')
    assert not looks_like_leaf_document_url('https://milvus.io/docs/zh/')

    scope = evaluate_seed_scope(
        'https://milvus.io/docs/zh/milvus-webui.md',
        _milvus_config(),
        pages_yielded=1,
        pages_in_scope=1,
        outbound_in_scope_count=0,
    )
    assert scope['seed_in_scope'] is True
    assert 'NO_IN_SCOPE_EXPANSION' not in scope['issues']
    assert scope['expansion_ok'] is True


def test_negative_max_depth_still_intends_multi_page():
    """LLM 写 max_depth=-1 仍视为多页意图，出链为 0 时应拦 NO_IN_SCOPE_EXPANSION"""
    config = {
        'crawler_run_config': {
            'deep_crawl_strategy': {
                'max_depth': -1,
                'max_pages': None,
                'filter_chain': {
                    'include_patterns': ['https://milvus.io/docs/zh/*'],
                    'exclude_patterns': [],
                },
            },
        },
    }
    scope = evaluate_seed_scope(
        'https://milvus.io/docs/zh/',
        config,
        pages_yielded=1,
        pages_in_scope=1,
        outbound_in_scope_count=0,
    )
    assert 'NO_IN_SCOPE_EXPANSION' in scope['issues']


def test_extract_filter_chain_nested():
    fc = extract_filter_chain(_milvus_config())
    assert fc is not None
    assert 'https://milvus.io/docs/zh/*' in fc['include_patterns']


def test_quality_gate_flags_seed_mismatch():
    gate = TrialQualityGateService.evaluate(
        success=True,
        title='Milvus',
        markdown='# Hello\n' + ('正文 ' * 80),
        status_code=200,
        seed_url='https://milvus.io/zh',
        crawl_config=_milvus_config(),
        page_results=[
            {
                'url': 'https://milvus.io/zh',
                'success': True,
                'links': {'internal': [{'href': 'https://milvus.io/docs/zh/quickstart.md'}]},
                'markdown': '[quickstart](https://milvus.io/docs/zh/quickstart.md)',
            },
            {
                'url': 'https://milvus.io/docs/zh/quickstart.md',
                'success': True,
                'links': {'internal': []},
                'markdown': '# Quickstart',
            },
        ],
    )
    assert gate.passed is False
    assert 'SEED_SCOPE_MISMATCH' in gate.issues
    assert gate.expansion_ok is False
    assert gate.pages_in_scope == 1
    assert gate.outbound_in_scope_count == 1
