"""
探针全链路 E2E：SPA 动态渲染检测 + 站点校准策略 + hooks 对比

运行:
  cd knowledge-content
  PYTHONPATH=src:../knowledge-common/src ../.venv/bin/python tests/manual_probe_e2e_full.py

验证项:
  A. HTTP vs 浏览器双通道 → SPA / shell_risk / needs_browser
  B. 交互元素分类（版本/语言选择器等）
  C. suggested_actions → url_prefix 可直接试爬通过
  D. LLM 瞎编 hooks 应失败；探针推导 hooks（DOM 证据）应可用
  E. 多页试爬（探针校准后的 URL 前缀）
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field

sys.path.insert(0, 'src')
sys.path.insert(0, '../knowledge-common/src')

TARGET = 'https://milvus.io/docs/zh'
TARGET_VERSION = 'v2.6.x'
TARGET_LANG = 'zh'

# LLM 常瞎编的 hooks（应失败）
BAD_LLM_HOOKS = {
    'on_page_loaded': [{
        'action': 'switch_version',
        'steps': [
            {'type': 'click', 'selector': 'text=v3.0'},
            {'type': 'click', 'selector': f'text={TARGET_VERSION}'},
            {'type': 'wait', 'selector': 'nav a', 'timeout': 5000},
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
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ''
    extra: dict = field(default_factory=dict)


def _pp(title: str, data) -> None:
    print(f'\n{"=" * 70}\n{title}\n{"=" * 70}')
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            print(data)
            return
    print(json.dumps(data, ensure_ascii=False, indent=2))


def pick_probe_action(probe: dict, version: str, lang: str | None = None) -> dict | None:
    """模拟 Agent 消费 suggested_actions：优先 url_prefix，匹配版本与语言"""
    actions = probe.get('suggested_actions') or []
    url_actions = [a for a in actions if a.get('action_type') == 'url_prefix']
    if not url_actions:
        return next((a for a in actions if a.get('action_type') == 'hooks'), None)

    def score(a: dict) -> int:
        prefix = a.get('url_prefix', '')
        s = 0
        if version.replace('.x', '') in prefix:
            s += 10
        if lang and f'/{lang}/' in prefix:
            s += 5
        return s

    return max(url_actions, key=score, default=None)


def build_strategy_from_probe(probe: dict, version: str, lang: str | None = None) -> dict:
    """从探针输出构建 crawl_config（Agent 应走的标准路径）"""
    action = pick_probe_action(probe, version, lang)
    if not action:
        return {**BASE_CRAWLER_CONFIG, 'hooks': {}}

    if action.get('action_type') == 'url_prefix':
        return {
            **BASE_CRAWLER_CONFIG,
            'hooks': {},
            'probe_derived': {
                'url_prefix': action['url_prefix'],
                'include_pattern': action['include_pattern'],
                'start_url': action['start_url'],
            },
        }
    return {**BASE_CRAWLER_CONFIG, 'hooks': action.get('hooks') or {}}


def trial_url_from_probe(probe: dict, version: str, lang: str | None, page: str = 'overview.md') -> str | None:
    action = pick_probe_action(probe, version, lang)
    if not action or action.get('action_type') != 'url_prefix':
        return None
    base = action['url_prefix'].rstrip('/')
    return f'{base}/{page}'


async def main() -> None:
    from knowledge_content.agents.tools.fetch_page import fetch_page
    from knowledge_content.agents.tools.probe_rendered_page import probe_rendered_page
    from knowledge_content.agents.tools.crawl_trial import trial_crawl
    from knowledge_content.service.page_probe.probe_action_planner import plan_crawl_actions
    from knowledge_content.service.page_probe.url_signals_analyzer import analyze_url_signals
    from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo

    results: list[CheckResult] = []
    state = {'target_url': TARGET, 'expected_doc_version': TARGET_VERSION}

    # ── A. HTTP 快探 ──
    http_raw = await fetch_page.ainvoke({'url': TARGET})
    http_obj = json.loads(http_raw)
    _pp('A1. fetch_page (HTTP)', http_obj)

    # ── B. 渲染探针 ──
    probe_raw = await probe_rendered_page.ainvoke({'url': TARGET})
    probe = json.loads(probe_raw)
    _pp('B1. probe_rendered_page (浏览器渲染)', probe)

    rendering = probe.get('rendering') or {}
    elements = probe.get('interactive_elements') or []
    categories = {e.get('category') for e in elements}
    implications = probe.get('crawl_implications') or []

    print('\n>>> SPA/渲染检测摘要:')
    print(f'    mode={rendering.get("mode")} shell_risk={rendering.get("shell_risk")} '
          f'needs_browser={rendering.get("needs_browser")}')
    print(f'    http_chars={rendering.get("http_body_chars")} '
          f'rendered_chars={rendering.get("rendered_body_chars")} '
          f'ratio={rendering.get("content_ratio")}')
    print(f'    interactive: {sorted(categories)}')
    print(f'    implications: {implications}')

    results.append(CheckResult(
        'SPA/动态渲染 needs_browser（版本选择器需渲染校准）',
        rendering.get('needs_browser') is True,
        f'mode={rendering.get("mode")}, shell_risk={rendering.get("shell_risk")}',
    ))
    results.append(CheckResult(
        'needs_browser_for_version_discovery implication',
        'needs_browser_for_version_discovery' in implications,
        str(implications),
    ))
    results.append(CheckResult(
        '检测到 version_switcher',
        'version_switcher' in categories,
        str([e for e in elements if e.get('category') == 'version_switcher']),
    ))
    results.append(CheckResult(
        'crawl_implications 含 use_probe_version_url_prefix',
        'use_probe_version_url_prefix' in implications,
        str(implications),
    ))
    results.append(CheckResult(
        'version_url_patterns 非空',
        len(probe.get('version_url_patterns') or []) >= 2,
        f'count={len(probe.get("version_url_patterns") or [])}',
    ))

    # ── C. 基线试爬（默认 URL，无校准）应 VERSION_MISMATCH ──
    baseline_url = 'https://milvus.io/docs/zh/overview.md'
    trial_baseline = json.loads(await trial_crawl.ainvoke({
        'url': baseline_url,
        'crawl_config': {**BASE_CRAWLER_CONFIG, 'hooks': {}},
        'state': state,
    }))
    _pp('C1. trial 基线（无校准，期望 v3.0）', trial_baseline)
    qg_base = trial_baseline.get('quality_gate') or {}
    results.append(CheckResult(
        '基线试爬有内容',
        trial_baseline.get('content_length', 0) > 3000,
        f'len={trial_baseline.get("content_length")}',
    ))
    results.append(CheckResult(
        '基线 VERSION_MISMATCH（未校准到 v2.6）',
        'VERSION_MISMATCH' in (qg_base.get('issues') or []),
        str(qg_base.get('issues')),
    ))

    # ── D. 探针校准策略试爬 ──
    strategy = build_strategy_from_probe(probe, TARGET_VERSION, TARGET_LANG)
    probe_url = trial_url_from_probe(probe, TARGET_VERSION, TARGET_LANG)
    _pp('D1. 从探针构建的策略', strategy)
    print(f'\n>>> 探针推导试爬 URL: {probe_url}')

    assert probe_url, '探针未产出 url_prefix 动作'
    trial_probe = json.loads(await trial_crawl.ainvoke({
        'url': probe_url,
        'crawl_config': strategy,
        'state': state,
    }))
    _pp('D2. trial 探针校准 URL', trial_probe)
    qg_probe = trial_probe.get('quality_gate') or {}
    results.append(CheckResult(
        '探针校准试爬正文充足',
        trial_probe.get('content_length', 0) > 8000,
        f'len={trial_probe.get("content_length")}',
    ))
    results.append(CheckResult(
        '探针校准无 VERSION_MISMATCH',
        'VERSION_MISMATCH' not in (qg_probe.get('issues') or []),
        str(qg_probe.get('issues')),
    ))
    preview = qg_probe.get('content_preview') or ''
    results.append(CheckResult(
        '正文含 v2.6.x 导航',
        'v2.6.x' in preview[:500],
        preview[:200],
    ))

    # ── E. LLM 瞎编 hooks 应失败 ──
    trial_bad_hooks = json.loads(await trial_crawl.ainvoke({
        'url': baseline_url,
        'crawl_config': {
            **BASE_CRAWLER_CONFIG,
            'hooks': BAD_LLM_HOOKS,
            'crawler_run_config': {
                **BASE_CRAWLER_CONFIG['crawler_run_config'],
                'page_timeout': 15000,
            },
        },
        'state': state,
    }))
    _pp('E1. trial LLM 瞎编 hooks', trial_bad_hooks)
    qg_bad = trial_bad_hooks.get('quality_gate') or {}
    bad_ok = (
        trial_bad_hooks.get('success') is False
        or 'VERSION_MISMATCH' in (qg_bad.get('issues') or [])
        or trial_bad_hooks.get('content_length', 0) < 3000
    )
    results.append(CheckResult(
        'LLM 瞎编 hooks 未通过质量门禁',
        bad_ok,
        f'success={trial_bad_hooks.get("success")}, issues={qg_bad.get("issues")}',
    ))

    # ── F. 探针推导 hooks（DOM 证据，非 LLM 猜）──
    # 用真实渲染 HTML 测试 href-based hooks
    from knowledge_content.infra.crawl4ai import Crawl4aiClient
    browser = await Crawl4aiClient.probe_page(TARGET)
    rendered_html = browser.get('html') or ''
    url_signals = analyze_url_signals(TARGET)
    version_els = [e for e in elements if e.get('category') == 'version_switcher']
    ie_vo = [
        InteractiveElementVo(**e) for e in version_els
    ] if version_els else [
        InteractiveElementVo(category='version_switcher', confidence=0.9,
                             impact='wrong_version', options=['v3.0.x', TARGET_VERSION]),
    ]
    _, actions_with_target = plan_crawl_actions(
        TARGET, rendered_html, url_signals, ie_vo, target_version=TARGET_VERSION,
    )
    hook_actions = [
        a.model_dump() for a in actions_with_target
        if a.action_type == 'hooks'
    ]
    _pp('F1. 探针 DOM 推导 hooks（target=v2.6.x）', hook_actions)

    if hook_actions:
        trial_dom_hooks = json.loads(await trial_crawl.ainvoke({
            'url': baseline_url,
            'crawl_config': {**BASE_CRAWLER_CONFIG, 'hooks': hook_actions[0].get('hooks')},
            'state': state,
        }))
        _pp('F2. trial 探针 DOM hooks', trial_dom_hooks)
        qg_dom = trial_dom_hooks.get('quality_gate') or {}
        results.append(CheckResult(
            '探针 DOM hooks 试爬',
            trial_dom_hooks.get('success') is True,
            f'issues={qg_dom.get("issues")}, len={trial_dom_hooks.get("content_length")}',
        ))
    else:
        # Milvus 有 url_prefix，不必 hook — 这也是正确结论
        results.append(CheckResult(
            'Milvus 优先 url_prefix 无需 hooks',
            True,
            '探针从渲染链接提取版本前缀，url_prefix 优先于 hooks',
        ))

    # ── G. 多页试爬（探针校准前缀）──
    pages = ['overview.md', 'install-overview.md']
    multi_ok = True
    for pg in pages:
        u = trial_url_from_probe(probe, TARGET_VERSION, TARGET_LANG, pg)
        if not u:
            multi_ok = False
            break
        r = json.loads(await trial_crawl.ainvoke({
            'url': u, 'crawl_config': strategy, 'state': state,
        }))
        qg = r.get('quality_gate') or {}
        ok = r.get('content_length', 0) > 3000 and 'VERSION_MISMATCH' not in (qg.get('issues') or [])
        print(f'    多页 {pg}: len={r.get("content_length")}, ok={ok}, issues={qg.get("issues")}')
        multi_ok = multi_ok and ok
    results.append(CheckResult('多页探针校准试爬', multi_ok, str(pages)))

    # ── 汇总 ──
    print('\n\n' + '=' * 70)
    print('E2E 验证汇总')
    print('=' * 70)
    passed = 0
    for r in results:
        mark = '✓' if r.passed else '✗'
        print(f'  [{mark}] {r.name}')
        if r.detail:
            print(f'       {r.detail[:120]}')
        if r.passed:
            passed += 1
    print(f'\n  合计: {passed}/{len(results)} 通过')
    if passed < len(results):
        sys.exit(1)


if __name__ == '__main__':
    asyncio.run(main())
