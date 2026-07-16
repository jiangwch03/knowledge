"""
Milvus 文档站探针 + hooks 真实联调（手动执行）

运行:
  cd knowledge-content
  PYTHONPATH=src:../knowledge-common/src ../.venv/bin/python tests/manual_milvus_probe_e2e.py
"""

import asyncio
import json
import sys

sys.path.insert(0, 'src')
sys.path.insert(0, '../knowledge-common/src')

TARGET = 'https://milvus.io/docs/zh'
PAGES = [
    'https://milvus.io/docs/zh/overview.md',
    'https://milvus.io/docs/zh/install-overview.md',
]

# 目标：简体中文 v2.6.x（需版本选择器 hook）
TARGET_VERSION = 'v2.6.x'
HOOKS_V26 = {
    'on_page_loaded': [{
        'action': 'switch_version',
        'steps': [
            {'type': 'click', 'selector': 'text=v3.0'},
            {'type': 'click', 'selector': f'text={TARGET_VERSION}'},
            {'type': 'wait', 'selector': 'nav a', 'timeout': 10000},
        ],
    }],
}

BASE_CRAWLER_CONFIG = {
    'browser_config': {'headless': True, 'enable_stealth': True},
    'crawler_run_config': {
        'cache_mode': 'BYPASS',
        'page_timeout': 60000,
        'wait_until': 'domcontentloaded',
        'word_count_threshold': 10,
        'stream': False,
    },
    'hooks': HOOKS_V26,
}


def _pp(title: str, data) -> None:
    print(f'\n{"=" * 60}\n{title}\n{"=" * 60}')
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            print(data)
            return
    print(json.dumps(data, ensure_ascii=False, indent=2))


async def main() -> None:
    from knowledge_content.agents.tools.fetch_page import fetch_page
    from knowledge_content.agents.tools.probe_rendered_page import probe_rendered_page
    from knowledge_content.agents.tools.crawl_trial import trial_crawl
    from knowledge_content.infra.crawl4ai import Crawl4aiClient

    # ── 1. HTTP 快探 ──
    http_result = await fetch_page.ainvoke({'url': TARGET})
    _pp('1. fetch_page (HTTP 快探)', http_result)

    # ── 2. 渲染探针 ──
    probe_result = await probe_rendered_page.ainvoke({'url': TARGET})
    _pp('2. probe_rendered_page (渲染探针)', probe_result)

    probe_obj = json.loads(probe_result)
    elements = probe_obj.get('interactive_elements', [])
    categories = [e.get('category') for e in elements]
    implications = probe_obj.get('crawl_implications', [])
    print(f'\n>>> 探测到的交互类型: {categories}')
    print(f'>>> crawl_implications: {implications}')
    print(f'>>> version_switcher: {"version_switcher" in categories}')
    print(f'>>> language_switcher: {"language_switcher" in categories}')

    state = {'target_url': TARGET, 'expected_doc_version': TARGET_VERSION}

    # ── 3. 试爬：无 hooks（基线，应为 v3.0）──
    no_hook_config = {
        **BASE_CRAWLER_CONFIG,
        'hooks': {},
    }
    trial_baseline = await trial_crawl.ainvoke({
        'url': PAGES[0],
        'crawl_config': no_hook_config,
        'state': state,
    })
    _pp('3. trial_crawl 无 hooks（基线 v3.0）', trial_baseline)

    # ── 4. 试爬：带版本切换 hooks（目标 v2.6）──
    trial_hooked = await trial_crawl.ainvoke({
        'url': PAGES[0],
        'crawl_config': BASE_CRAWLER_CONFIG,
        'state': state,
    })
    _pp('4. trial_crawl 带 v2.6 hooks', trial_hooked)

    hooked_obj = json.loads(trial_hooked)
    preview = (hooked_obj.get('quality_gate') or {}).get('content_preview', '')
    print(f'\n>>> hooks 试爬正文预览（前200字）:\n{preview[:200]}')
    print(f'>>> quality_gate.passed: {(hooked_obj.get("quality_gate") or {}).get("passed")}')
    print(f'>>> issues: {(hooked_obj.get("quality_gate") or {}).get("issues")}')

    # ── 5. 再爬第 2 页验证 hooks 在多页是否生效 ──
    trial_page2 = await trial_crawl.ainvoke({
        'url': PAGES[1],
        'crawl_config': BASE_CRAWLER_CONFIG,
        'state': state,
    })
    _pp('5. trial_crawl 第2页（install-overview）带 hooks', trial_page2)

    # ── 6. 直接 Crawl4aiClient 验证 hook 参数合并 ──
    from knowledge_content.agents.utils.hook_adapter import hooks_to_crawl_params
    hook_params = hooks_to_crawl_params(HOOKS_V26)
    _pp('6. hooks → crawl4ai 参数', hook_params)

    print('\n\n========== 联调结论 ==========')
    baseline_obj = json.loads(trial_baseline)
    for label, obj in [('基线(无hook)', baseline_obj), ('hooks v2.6', hooked_obj)]:
        qg = obj.get('quality_gate') or {}
        print(
            f'{label}: content_length={obj.get("content_length")}, '
            f'passed={qg.get("passed")}, issues={qg.get("issues")}',
        )


if __name__ == '__main__':
    asyncio.run(main())
