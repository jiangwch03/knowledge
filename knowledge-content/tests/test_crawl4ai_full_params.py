"""
crawl4ai 全参数覆盖集成测试

目标：以 milvus.io 中文文档为例，验证全链路：
  Phase 1: Crawl4aiConfigBuilder dict→Python对象构建（SDK 侧验证）
           Crawl4aiConfigBuilder dict→{type,params} 序列化（Service 侧验证）
  Phase 2: Service 模式流式爬取（通过 /crawl/stream 端点，验证 NDJSON 流解析）
  Phase 3: Crawl4aiClient.crawl_stream 门面流式爬取（沿用当前配置模式）
  Phase 4: 裸 HTTP 调用 /crawl/stream 验证 NDJSON 原始格式（流结束信号等）

所有参数均动态构建，不 mock，真实爬取。

运行方式：
  cd knowledge && python knowledge-content/tests/test_crawl4ai_full_params.py
"""

import asyncio
import json
import sys
import time

sys.path.insert(0, 'knowledge-content/src')
sys.path.insert(0, 'knowledge-common/src')

import httpx

# ─── crawl4ai 库导入（仅 Phase 1 构建验证用） ────────────────────
from crawl4ai import CacheMode, MatchMode
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

# ─── 项目内部导入 ──────────────────────────────────────────────
from knowledge_content.infra.crawl4ai._crawl4ai_config_builder import Crawl4aiConfigBuilder
from knowledge_content.infra.crawl4ai._crawl4ai_service_client import _Crawl4aiServiceClient
from knowledge_content.infra.crawl4ai.crawl4ai_client import Crawl4aiClient

# ─── 测试常量 ──────────────────────────────────────────────────
TARGET_URL = 'https://milvus.io/docs/zh/overview.md'
MILVUS_ZH_PATTERN = 'https://milvus.io/docs/zh/*'

# 模拟 LLM 生成的全参数 JSON 配置（声明式 dict）
# Service 模式下复杂对象会通过 serialize_crawl_config 转换为 {type, params} 序列化格式
# SDK 模式下会通过 ConfigBuilder 构建为 Python 对象
FULL_CRAWL_CONFIG: dict = {
    # ═══ 1. 基本类型参数 ═══
    'word_count_threshold': 10,
    'only_text': False,
    'excluded_tags': ['nav', 'footer', 'header', 'aside', 'script', 'style', 'form', 'iframe'],
    'semaphore_count': 2,
    'stream': True,
    'verbose': False,

    # ═══ 2. 枚举参数（字符串 → 枚举值） ═══
    'cache_mode': 'BYPASS',
    'match_mode': 'OR',

    # ═══ 3. 复杂对象：markdown_generator（嵌套 content_filter） ═══
    'markdown_generator': {
        'type': 'DefaultMarkdownGenerator',
        'content_filter': {
            'type': 'PruningContentFilter',
            'threshold': 0.3,
            'threshold_type': 'fixed',
        },
    },

    # ═══ 4. 深度爬取策略（deep_crawl_strategy + filter_chain） ═══
    'deep_crawl_strategy': {
        'crawl_strategy': 'BFSDeepCrawlStrategy',
        'max_depth': 1,
        'include_external': False,
        'max_pages': 3,
        'filter_chain': {
            'include_patterns': [MILVUS_ZH_PATTERN],
            'exclude_patterns': ['*/api/*', '*/community/*'],
        },
    },

    # ═══ 5. 反爬参数（即使目标站无反爬也要验证参数不报错） ═══
    'remove_overlay_elements': True,
    'remove_consent_popups': True,
    'simulate_user': True,
    'override_navigator': True,
    'magic': True,
    'delay_before_return_html': 0.5,
    'mean_delay': 0.2,
    'max_range': 0.3,
    'max_retries': 1,

    # ═══ 6. 内容过滤参数 ═══
    'excluded_selector': '.sidebar, .toc',
    'exclude_external_links': True,
    'exclude_social_media_links': True,
    'exclude_external_images': True,

    # ═══ 7. 页面控制参数 ═══
    'page_timeout': 30000,
    'wait_until': 'domcontentloaded',
    'wait_for_images': False,
    'flatten_shadow_dom': False,
    'process_iframes': False,
    'scan_full_page': False,
    'scroll_delay': 0.1,
}


def test_config_builder() -> dict:
    """Phase 1: 验证 ConfigBuilder 的 dict→Python对象构建"""
    print('=' * 70)
    print('Phase 1: ConfigBuilder 参数构建验证')
    print('=' * 70)

    result = Crawl4aiConfigBuilder.build_crawl_config(FULL_CRAWL_CONFIG)
    errors: list[str] = []

    # 1. 基本类型参数透传
    for key in ('word_count_threshold', 'only_text', 'excluded_tags', 'semaphore_count',
                'stream', 'verbose', 'excluded_selector',
                'remove_overlay_elements', 'remove_consent_popups', 'simulate_user',
                'override_navigator', 'magic', 'delay_before_return_html',
                'mean_delay', 'max_range', 'max_retries',
                'exclude_external_links', 'exclude_social_media_links', 'exclude_external_images',
                'page_timeout', 'wait_until', 'wait_for_images',
                'flatten_shadow_dom', 'process_iframes', 'scan_full_page', 'scroll_delay'):
        if key not in result:
            errors.append(f'[基本类型] {key} 丢失')
        elif result[key] != FULL_CRAWL_CONFIG[key]:
            errors.append(f'[基本类型] {key} 值被篡改')
    print(f'  [1/6] 基本类型参数透传: {"PASS" if not errors else "FAIL"}')

    # 2. 枚举转换
    cache_ok = isinstance(result.get('cache_mode'), CacheMode) and result['cache_mode'] == CacheMode.BYPASS
    match_ok = isinstance(result.get('match_mode'), MatchMode) and result['match_mode'] == MatchMode.OR
    if not (cache_ok and match_ok):
        errors.append(f'[枚举] 转换失败')
    print(f'  [2/6] 枚举转换: {"PASS" if cache_ok and match_ok else "FAIL"}')

    # 3. markdown_generator
    mg = result.get('markdown_generator')
    mg_ok = (isinstance(mg, DefaultMarkdownGenerator)
             and isinstance(mg.content_filter, PruningContentFilter)
             and mg.content_filter.threshold == 0.3)
    if not mg_ok:
        errors.append('[markdown_generator] 构建失败')
    print(f'  [3/6] markdown_generator: {"PASS" if mg_ok else "FAIL"} '
          f'({type(mg).__name__} + {type(mg.content_filter).__name__})')

    # 4. deep_crawl_strategy
    dcs = result.get('deep_crawl_strategy')
    dcs_ok = (isinstance(dcs, BFSDeepCrawlStrategy) and dcs.max_depth == 1
              and dcs.max_pages == 3 and dcs.include_external is False)
    if not dcs_ok:
        errors.append('[deep_crawl_strategy] 构建失败')
    print(f'  [4/6] deep_crawl_strategy: {"PASS" if dcs_ok else "FAIL"} '
          f'({type(dcs).__name__}, depth={dcs.max_depth}, pages={dcs.max_pages})')

    # 5. filter_chain
    fc = dcs.filter_chain if dcs else None
    fc_ok = isinstance(fc, FilterChain) and len(fc.filters) == 2
    if not fc_ok:
        errors.append('[filter_chain] 构建失败')
    print(f'  [5/6] filter_chain: {"PASS" if fc_ok else "FAIL"} (filters={len(fc.filters) if fc else 0})')

    # 6. serialize（Service 模式：{type, params} 序列化格式）
    serialized = Crawl4aiConfigBuilder.serialize_crawl_config(FULL_CRAWL_CONFIG)

    # 基本类型参数透传
    ser_basic_ok = (serialized.get('word_count_threshold') == 10
                    and serialized.get('stream') is True
                    and serialized.get('excluded_tags') == FULL_CRAWL_CONFIG['excluded_tags'])

    # 枚举字段序列化为 {type, params} 格式（params 为枚举 value，小写）
    ser_cache_ok = (serialized.get('cache_mode') == {'type': 'CacheMode', 'params': 'bypass'})
    ser_match_ok = (serialized.get('match_mode') == {'type': 'MatchMode', 'params': 'or'})

    # markdown_generator 序列化为 {type, params} 嵌套格式
    ser_mg = serialized.get('markdown_generator', {})
    ser_mg_ok = (ser_mg.get('type') == 'DefaultMarkdownGenerator'
                 and isinstance(ser_mg.get('params'), dict)
                 and ser_mg['params'].get('content_filter', {}).get('type') == 'PruningContentFilter'
                 and ser_mg['params']['content_filter'].get('params', {}).get('threshold') == 0.3)

    # deep_crawl_strategy 序列化为 {type, params} 嵌套格式
    ser_dcs = serialized.get('deep_crawl_strategy', {})
    ser_dcs_ok = (ser_dcs.get('type') == 'BFSDeepCrawlStrategy'
                  and isinstance(ser_dcs.get('params'), dict)
                  and ser_dcs['params'].get('max_depth') == 1
                  and ser_dcs['params'].get('max_pages') == 3)

    # filter_chain 序列化为 {type: "FilterChain", params: {filters: [...]}}
    ser_fc = ser_dcs.get('params', {}).get('filter_chain', {})
    ser_fc_ok = (ser_fc.get('type') == 'FilterChain'
                 and isinstance(ser_fc.get('params', {}).get('filters'), list)
                 and len(ser_fc['params']['filters']) == 2
                 and ser_fc['params']['filters'][0].get('type') == 'URLPatternFilter')

    ser_all_ok = ser_basic_ok and ser_cache_ok and ser_match_ok and ser_mg_ok and ser_dcs_ok and ser_fc_ok
    if not ser_all_ok:
        errors.append(f'[serialize] 序列化验证失败: basic={ser_basic_ok}, cache={ser_cache_ok}, '
                      f'match={ser_match_ok}, mg={ser_mg_ok}, dcs={ser_dcs_ok}, fc={ser_fc_ok}')
    print(f'  [6/6] Service serialize: {"PASS" if ser_all_ok else "FAIL"}')
    if not ser_all_ok:
        print(f'    cache_mode: {serialized.get("cache_mode")}')
        print(f'    markdown_generator: {serialized.get("markdown_generator")}')
        print(f'    deep_crawl_strategy: {serialized.get("deep_crawl_strategy")}')

    status = 'ALL PASSED' if not errors else f'FAILED ({len(errors)} errors)'
    print(f'\n  Phase 1 {status}')
    if errors:
        for e in errors:
            print(f'    - {e}')
    return result


def _print_results(phase_name: str, results, elapsed: float) -> bool:
    """通用结果打印与验证"""
    print(f'\n  [爬取完成] {elapsed:.1f}s, 结果数量: {len(results)}')

    for i, r in enumerate(results):
        print(f'\n  ── 结果 [{i+1}] ──')
        print(f'    success: {r.success}')
        print(f'    url: {r.url}')
        if r.success:
            md_len = len(r.markdown) if r.markdown else 0
            print(f'    title: {r.title or "(空)"}')
            print(f'    markdown 长度: {md_len} 字符')
            if r.markdown:
                preview = r.markdown[:200].replace('\n', ' | ')
                print(f'    预览: {preview}...')
        else:
            print(f'    error_code: {r.error_code}')
            print(f'    error_message: {r.error_message}')

    success_count = sum(1 for r in results if r.success)
    if success_count > 0:
        for r in results:
            if r.success and r.markdown:
                has_milvus = 'milvus' in r.markdown.lower() or '向量' in r.markdown
                print(f'\n  内容相关性: {"PASS" if has_milvus else "WARN"} (含Milvus关键词={has_milvus})')
        print(f'\n  {phase_name} PASSED ({success_count}/{len(results)} 页成功)')
        return True
    else:
        print(f'\n  {phase_name} FAILED (全部失败)')
        return False


async def test_service_crawl_stream() -> bool:
    """Phase 2: Service 模式流式爬取（通过 /crawl/stream 端点）"""
    print('\n' + '=' * 70)
    print('Phase 2: Service 模式流式爬取')
    print(f'  目标: {TARGET_URL}')
    print(f'  参数数量: {len(FULL_CRAWL_CONFIG)} 个')
    print('=' * 70)

    # 展示 serialize 后的配置（Service 模式实际发送的内容）
    serialized = Crawl4aiConfigBuilder.serialize_crawl_config(FULL_CRAWL_CONFIG)
    print(f'\n  [serialize 后发送的参数] ({len(serialized)} 个):')
    for k, v in serialized.items():
        print(f'    {k}: {v}')

    print(f'\n  [开始流式爬取]...')
    results: list = []
    start = time.time()

    async for result in _Crawl4aiServiceClient.crawl_stream(TARGET_URL, FULL_CRAWL_CONFIG):
        results.append(result)
        md_len = len(result.markdown) if result.success and result.markdown else 0
        status = 'OK' if result.success else f'FAIL({result.error_code})'
        print(f'  流结果[{len(results)}]: {status}, url={result.url[:60]}..., markdown_len={md_len}')

    elapsed = time.time() - start
    return _print_results('Phase 2 (Service 流式)', results, elapsed)


async def test_facade_crawl_stream() -> bool:
    """Phase 3: Crawl4aiClient.crawl_stream 门面流式爬取"""
    print('\n' + '=' * 70)
    print('Phase 3: Crawl4aiClient.crawl_stream 门面流式爬取')
    print(f'  目标: {TARGET_URL}')
    print(f'  参数数量: {len(FULL_CRAWL_CONFIG)} 个')
    print('=' * 70)

    print(f'\n  [开始门面流式爬取]...')
    results: list = []
    start = time.time()

    async for result in Crawl4aiClient.crawl_stream(TARGET_URL, FULL_CRAWL_CONFIG):
        results.append(result)
        md_len = len(result.markdown) if result.success and result.markdown else 0
        status = 'OK' if result.success else f'FAIL({result.error_code})'
        print(f'  流结果[{len(results)}]: {status}, url={result.url[:60]}..., markdown_len={md_len}')

    elapsed = time.time() - start
    return _print_results('Phase 3 (Facade)', results, elapsed)


async def test_bare_http_stream() -> bool:
    """Phase 4: 裸 HTTP 调用 /crawl/stream，验证 NDJSON 原始格式"""
    print('\n' + '=' * 70)
    print('Phase 4: 裸 HTTP 流式验证（NDJSON 格式）')
    print(f'  目标: {TARGET_URL}')
    print('=' * 70)

    payload = {
        'urls': [TARGET_URL],
        'browser_config': {'headless': True},
        'crawler_config': {'stream': True},
    }
    endpoint = 'http://localhost:11235/crawl/stream'

    count = 0
    has_completed = False
    has_success = False

    async with httpx.AsyncClient() as client:
        async with client.stream('POST', endpoint, json=payload, timeout=120) as resp:
            print(f'  HTTP 状态码: {resp.status_code}')
            if resp.status_code != 200:
                print(f'  FAIL: HTTP {resp.status_code}')
                return False

            async for line in resp.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)

                if item.get('status') == 'completed':
                    has_completed = True
                    print(f'  LINE{count}: [completed] 流结束信号')
                elif item.get('success'):
                    has_success = True
                    md = item.get('markdown', '') or ''
                    md_len = len(md) if isinstance(md, str) else 0
                    print(f'  LINE{count}: [success] url={item.get("url","?")}, '
                          f'markdown_len={md_len}, title={item.get("title","?")}')
                else:
                    print(f'  LINE{count}: [failed] url={item.get("url","?")}, '
                          f'error={item.get("error_message","?")}')
                count += 1

    print(f'\n  总计接收行数: {count}')
    print(f'  成功结果: {has_success}')
    print(f'  流结束信号: {has_completed}')

    ok = count >= 2 and has_success and has_completed
    print(f'  Phase 4: {"PASS" if ok else "FAIL"}')
    return ok


def main():
    print('crawl4ai 全参数覆盖集成测试（真实爬取，无 mock）')
    print(f'目标 URL: {TARGET_URL}\n')

    # Phase 1: ConfigBuilder 构建验证（同步执行）
    test_config_builder()

    # Phase 2-4: 流式爬取验证（异步执行）
    results = asyncio.run(_run_crawl_phases())

    print('\n' + '=' * 70)
    print(f'总结: Service流式={results[0]}, Facade={results[1]}, 裸HTTP流={results[2]}')
    print('=' * 70)

    if not all(results):
        sys.exit(1)


async def _run_crawl_phases() -> tuple[bool, bool, bool]:
    p2 = await test_service_crawl_stream()
    p3 = await test_facade_crawl_stream()
    p4 = await test_bare_http_stream()
    return p2, p3, p4


if __name__ == '__main__':
    main()
