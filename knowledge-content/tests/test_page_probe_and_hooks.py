"""探针与 hooks 单元测试"""

import json

import pytest

from knowledge_content.agents.utils.hook_schema import validate_hooks
from knowledge_content.agents.utils.strategy_config_resolver import (
    merge_hook_params,
    resolve_strategy_config,
)
from knowledge_content.agents.utils.hook_adapter import hooks_to_crawl_params
from knowledge_content.service.page_probe.crawl_implications_engine import derive_crawl_implications
from knowledge_content.service.page_probe.rendering_analyzer import build_rendering_probe
from knowledge_content.service.page_probe.url_signals_analyzer import analyze_url_signals
from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.rendering_probe_vo import RenderingProbeVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo
from knowledge_content.service.trial_quality_gate_service import TrialQualityGateService


class TestUrlSignalsAnalyzer:
    def test_version_in_path(self):
        vo = analyze_url_signals('https://example.com/docs/v2.6.x/overview')
        assert vo.has_version_in_path is True
        assert vo.has_language_in_path is False

    def test_language_in_path(self):
        vo = analyze_url_signals('https://example.com/docs/zh/overview.md')
        assert vo.has_language_in_path is True


class TestRenderingAnalyzer:
    def test_spa_high_shell_risk(self):
        vo = build_rendering_probe(100, 8000)
        assert vo.mode == 'spa'
        assert vo.shell_risk == 'high'
        assert vo.needs_browser is True

    def test_hybrid_when_version_switcher_on_large_http(self):
        from knowledge_content.service.page_probe.rendering_analyzer import refine_rendering_for_interactions
        from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo

        base = build_rendering_probe(200_000, 120_000)
        assert base.mode == 'static'
        refined = refine_rendering_for_interactions(
            base,
            UrlSignalsVo(has_version_in_path=False, has_language_in_path=True),
            [InteractiveElementVo(category='version_switcher', confidence=0.8, impact='wrong_version')],
        )
        assert refined.mode == 'hybrid'
        assert refined.needs_browser is True


class TestCrawlImplications:
    def test_version_not_in_url(self):
        rendering = RenderingProbeVo(shell_risk='high', needs_browser=True)
        url_signals = UrlSignalsVo(has_version_in_path=False)
        elements = [
            InteractiveElementVo(
                category='version_switcher',
                confidence=0.85,
                impact='wrong_version_without_interaction',
                options=['v3.0.x', 'v2.6.x'],
            ),
        ]
        implications = derive_crawl_implications(rendering, url_signals, elements, version_url_patterns=[])
        assert 'version_not_in_url_ask_user' in implications
        assert 'needs_browser_for_version_discovery' in implications


class TestHookAdapter:
    def test_version_switch_hooks(self):
        hooks = {
            'on_page_loaded': [{
                'action': 'switch_version',
                'steps': [
                    {'type': 'click', 'selector': 'text=v3.0.x'},
                    {'type': 'click', 'selector': 'text=v2.6.x'},
                    {'type': 'wait', 'selector': 'nav a', 'timeout': 5000},
                ],
            }],
        }
        params = hooks_to_crawl_params(hooks)
        assert 'js_code_before_wait' in params
        assert len(params['js_code_before_wait']) == 2
        assert params['wait_for'] == 'css:nav a'


class TestStrategyConfigResolver:
    def test_nested_config(self):
        config = {
            'browser_config': {'headless': True},
            'crawler_run_config': {'page_timeout': 60000},
            'hooks': {},
        }
        browser, crawler, hooks = resolve_strategy_config(config)
        assert browser['headless'] is True
        assert crawler['page_timeout'] == 60000
        assert hooks == {}

    def test_merge_hooks_into_crawler(self):
        crawler = {'wait_until': 'domcontentloaded'}
        hooks = {
            'on_page_loaded': [{
                'steps': [{'type': 'wait', 'selector': '.content'}],
            }],
        }
        merged = merge_hook_params(crawler, hooks)
        assert merged['wait_until'] == 'domcontentloaded'
        assert merged['wait_for'] == 'css:.content'


class TestTrialQualityGate:
    def test_empty_shell(self):
        gate = TrialQualityGateService.evaluate(
            success=True,
            title='T',
            markdown='short',
            status_code=200,
        )
        assert gate.passed is False
        assert 'EMPTY_SHELL' in gate.issues

    def test_good_content(self):
        md = '# Title\n\n' + ('paragraph. ' * 100)
        gate = TrialQualityGateService.evaluate(
            success=True,
            title='Title',
            markdown=md,
            status_code=200,
        )
        assert gate.passed is True
        assert gate.heading_count >= 1

    def test_version_mismatch_active_nav_line(self):
        md = (
            '[首页](https://milvus.io/docs/zh)\n'
            'v3.0.x\n'
            '  * [v2.6.x](https://milvus.io/docs/v2.6.x/overview.md)\n\n'
            + ('Milvus v3.0.x documentation welcome. ' * 50)
        )
        gate = TrialQualityGateService.evaluate(
            success=True,
            title='Docs',
            markdown=md,
            status_code=200,
            expected_version='v2.6.x',
        )
        assert gate.passed is False
        assert 'VERSION_MISMATCH' in gate.issues

    def test_version_match_when_home_has_version(self):
        md = (
            '[首页](https://milvus.io/docs/zh/v2.6.x)\n'
            'v2.6.x\n'
            + ('Milvus overview content. ' * 50)
        )
        gate = TrialQualityGateService.evaluate(
            success=True,
            title='Docs',
            markdown=md,
            status_code=200,
            expected_version='v2.6.x',
        )
        assert 'VERSION_MISMATCH' not in gate.issues
