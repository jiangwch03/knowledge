"""
多站点探针联调：验证站点无关规则

运行:
  cd knowledge-content
  PYTHONPATH=src:../knowledge-common/src ../.venv/bin/python tests/manual_probe_multi_site.py [url ...]
"""

from __future__ import annotations

import asyncio
import json
import sys

sys.path.insert(0, 'src')
sys.path.insert(0, '../knowledge-common/src')

DEFAULT_SITES = [
    'https://docs.crawl4ai.com/',
    'https://www.runoob.com/fastapi/fastapi-tutorial.html',
]

BASE_CRAWLER_CONFIG = {
    'browser_config': {'headless': True, 'enable_stealth': True},
    'crawler_run_config': {
        'cache_mode': 'BYPASS',
        'page_timeout': 45000,
        'wait_until': 'domcontentloaded',
        'word_count_threshold': 10,
        'stream': False,
    },
}


def _summarize_probe(probe: dict) -> dict:
    rendering = probe.get('rendering') or {}
    elements = probe.get('interactive_elements') or []
    return {
        'mode': rendering.get('mode'),
        'shell_risk': rendering.get('shell_risk'),
        'needs_browser': rendering.get('needs_browser'),
        'http_chars': rendering.get('http_body_chars'),
        'rendered_chars': rendering.get('rendered_body_chars'),
        'ratio': rendering.get('content_ratio'),
        'interactive': [e.get('category') for e in elements],
        'implications': probe.get('crawl_implications'),
        'version_patterns': len(probe.get('version_url_patterns') or []),
        'site_types': [c.get('site_type') for c in (probe.get('site_type_candidates') or [])[:3]],
    }


async def probe_site(url: str) -> None:
    from knowledge_content.agents.tools.fetch_page import fetch_page
    from knowledge_content.agents.tools.probe_rendered_page import probe_rendered_page
    from knowledge_content.agents.tools.crawl_trial import trial_crawl

    print(f'\n{"#" * 72}\n# 站点: {url}\n{"#" * 72}')

    # 1. HTTP 快探
    http = json.loads(await fetch_page.ainvoke({'url': url}))
    print('\n[fetch_page]')
    print(f'  has_js_rendering={http.get("has_js_rendering")} '
          f'internal_links={http.get("internal_link_count")} '
          f'popup={http.get("popup_type")}')

    # 2. 渲染探针
    probe = json.loads(await probe_rendered_page.ainvoke({'url': url}))
    summary = _summarize_probe(probe)
    print('\n[probe_rendered_page]')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print('controls_count:', len(probe.get('controls', [])))
    for el in probe.get('interactive_elements', []):
        print(f"  - {el.get('category')}: fields={len(el.get('fields',[]))}")

    state = {'target_url': url}

    # 3. 基线试爬（同 URL，无 hooks）
    baseline = json.loads(await trial_crawl.ainvoke({
        'url': url,
        'crawl_config': {**BASE_CRAWLER_CONFIG, 'hooks': {}},
        'state': state,
    }))
    qg = baseline.get('quality_gate') or {}
    print('\n[trial 基线]')
    print(f'  success={baseline.get("success")} len={baseline.get("content_length")} '
          f'passed={qg.get("passed")} issues={qg.get("issues")}')
    preview = (qg.get('content_preview') or '')[:180]
    print(f'  preview: {preview}...')

    # 4. Agent 根据 interactive_elements 自行决策；此处仅做基线试爬
    print('\n[结论]')
    if summary['needs_browser']:
        print('  → 需要浏览器渲染')
    else:
        print('  → HTTP/SSR 即可，浏览器非必须')
    if probe.get('version_url_patterns'):
        print(f'  → 版本 URL 事实: {len(probe.get("version_url_patterns"))} 条')
    else:
        print('  → 无版本 URL 事实，由 Agent 读 interactive_elements 推理')


async def main() -> None:
    sites = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SITES
    for url in sites:
        await probe_site(url)
    print(f'\n{"=" * 72}\n完成 {len(sites)} 个站点探针\n{"=" * 72}')


if __name__ == '__main__':
    asyncio.run(main())
