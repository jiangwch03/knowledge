"""探针访问守卫与 crawl_config 组装测试"""

from knowledge_content.service.page_probe.probe_access_guard import (
    apply_probe_block_short_circuit,
    detect_probe_block,
    is_login_url,
    parse_intended_url,
)
from knowledge_content.service.page_probe.probe_crawl_config import (
    build_probe_crawl_config,
    cookies_to_hook_step,
)
from knowledge_content.service.vo.interactive_element_vo import (
    ControlFieldVo,
    InteractiveElementVo,
)
from knowledge_content.service.vo.rendered_page_probe_vo import RenderedPageProbeVo
from knowledge_content.service.vo.site_type_candidate_vo import SiteTypeCandidateVo


class TestProbeAccessGuard:
    def test_parse_redirect_param(self):
        actual = 'http://localhost/login?redirect=/knowledge/crawler'
        assert parse_intended_url('http://localhost/knowledge/crawler', actual) == (
            'http://localhost/knowledge/crawler'
        )

    def test_is_login_url(self):
        assert is_login_url('http://localhost/login?redirect=/x')
        assert not is_login_url('http://localhost/knowledge/crawler')

    def test_detect_login_redirect(self):
        reason, intended = detect_probe_block(
            'http://localhost/knowledge/crawler',
            'http://localhost/login?redirect=/knowledge/crawler',
            [],
        )
        assert reason == 'login_redirect'
        assert intended == 'http://localhost/knowledge/crawler'

    def test_detect_login_gate(self):
        elements = [InteractiveElementVo(category='login_gate', confidence=0.9)]
        reason, _ = detect_probe_block('http://example.com/app', 'http://example.com/app', elements)
        assert reason == 'login_required'

    def test_skip_block_when_auth_injected(self):
        elements = [InteractiveElementVo(category='login_gate', confidence=0.9)]
        reason, _ = detect_probe_block(
            'http://example.com/app', 'http://example.com/app', elements, auth_injected=True,
        )
        assert reason is None

    def test_short_circuit_clears_site_type(self):
        vo = RenderedPageProbeVo(
            url='http://localhost/knowledge/crawler',
            block_reason='login_redirect',
            intended_url='http://localhost/knowledge/crawler',
            actual_url='http://localhost/login?redirect=/knowledge/crawler',
            interactive_elements=[
                InteractiveElementVo(
                    category='login_gate',
                    confidence=0.9,
                    fields=[ControlFieldVo(role='password', selector='input[type=password]')],
                ),
                InteractiveElementVo(category='search_box', confidence=0.8),
            ],
            site_type_candidates=[SiteTypeCandidateVo(site_type='SPA 应用', score=0.8)],
            crawl_implications=['ask_user_for_credentials', 'site_search_available'],
        )
        blocked = apply_probe_block_short_circuit(vo)
        assert blocked.probe_status == 'blocked'
        assert blocked.action_required == 'ask_user_then_trial_with_hooks'
        assert blocked.site_type_candidates == []
        assert {el.category for el in blocked.interactive_elements} == {'login_gate'}
        assert 'probe_target_unreachable' in blocked.crawl_implications
        assert 'stop_probe_use_trial_after_auth' in blocked.crawl_implications
        assert 'site_search_available' not in blocked.crawl_implications


class TestProbeCrawlConfig:
    def test_cookies_to_hook_step(self):
        step = cookies_to_hook_step('session=abc; token=xyz')
        assert step['type'] == 'evaluate'
        assert 'session=abc' in step['code']

    def test_build_probe_crawl_config_with_hooks_and_cookies(self):
        config = build_probe_crawl_config(
            hooks={'on_page_loaded': [{'steps': [{'type': 'click', 'selector': 'button'}]}]},
            cookies='session=abc',
        )
        assert config is not None
        steps = config['hooks']['on_page_loaded'][0]['steps']
        assert steps[0]['type'] == 'evaluate'
        assert steps[1]['type'] == 'click'
