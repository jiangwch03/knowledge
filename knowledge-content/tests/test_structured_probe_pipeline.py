"""结构化探针流水线单元测试（②③④层 + Agent 消费契约）"""

import json

import pytest

from knowledge_content.service.page_probe.control_extractor import extract_page_controls
from knowledge_content.service.page_probe.crawl4ai_probe_adapter import build_page_structure
from knowledge_content.service.page_probe.interaction_classifier import classify_interactions
from knowledge_content.service.page_probe.rendering_analyzer import build_rendering_probe
from knowledge_content.service.page_probe.site_type_scorer import score_site_types
from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.page_structure_vo import PageStructureVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo

LOGIN_HTML = """
<form>
  <input type="text" placeholder="账号" />
  <input type="password" placeholder="密码" />
  <input type="text" placeholder="验证码" />
  <button type="button" class="el-button el-button--primary">登录</button>
</form>
"""

SEARCH_HTML = """
<header>
  <input type="search" placeholder="搜索文档" />
  <button>搜索</button>
</header>
"""

PAGINATION_HTML = """
<div class="el-pagination">
  <button>下一页</button>
</div>
"""

DOCS_HTML = """
<nav><a href="/docs/a">A</a><a href="/docs/b">B</a></nav>
<a href="/docs/v2.6.x/home">v2.6.x</a>
<a href="/docs/v3.0.x/home">v3.0.x</a>
"""


class TestControlExtractor:
    def test_login_form_controls(self):
        controls = extract_page_controls(LOGIN_HTML)
        types = {c.control_type for c in controls}
        assert 'password' in types
        assert 'text' in types
        placeholders = {c.placeholder for c in controls}
        assert '账号' in placeholders
        assert '验证码' in placeholders

    def test_stable_selector_uses_placeholder(self):
        controls = extract_page_controls(LOGIN_HTML)
        pwd = next(c for c in controls if c.control_type == 'password')
        assert 'placeholder' in pwd.selector or 'password' in pwd.selector


class TestInteractionClassifier:
    def test_login_gate_with_fields(self):
        controls = extract_page_controls(LOGIN_HTML)
        elements = classify_interactions(LOGIN_HTML, '', controls, PageStructureVo())
        login = next(e for e in elements if e.category == 'login_gate')
        assert login.submit is not None
        roles = {f.role for f in login.fields}
        assert 'password' in roles
        assert 'username' in roles or 'captcha' in roles

    def test_search_box_trigger_mode(self):
        controls = extract_page_controls(SEARCH_HTML)
        elements = classify_interactions(SEARCH_HTML, '', controls, PageStructureVo())
        search = next(e for e in elements if e.category == 'search_box')
        assert search.trigger_mode == 'submit_on_button'
        assert search.fields[0].role == 'search_query'

    def test_pagination_numbered(self):
        controls = extract_page_controls(PAGINATION_HTML)
        elements = classify_interactions(PAGINATION_HTML, '下一页', controls, PageStructureVo())
        pag = next(e for e in elements if e.category == 'pagination')
        assert pag.mode in ('numbered', 'load_more')


class TestSiteTypeScorer:
    def test_docs_site_scores_high(self):
        rendering = build_rendering_probe(5000, 8000)
        url_signals = UrlSignalsVo(has_language_in_path=True, language_patterns=['/zh'])
        page_structure = PageStructureVo(internal_link_count=30)
        elements = [
            InteractiveElementVo(category='version_switcher', confidence=0.8),
            InteractiveElementVo(category='sidebar_navigation', confidence=0.8),
        ]
        candidates = score_site_types(
            'https://example.com/docs/zh', rendering, url_signals, page_structure, elements,
        )
        assert candidates
        assert candidates[0].site_type in ('技术文档站', 'SPA 应用')


class TestCrawl4aiProbeAdapter:
    def test_build_page_structure_from_links(self):
        probe = {
            'success': True,
            'title': 'T',
            'html': '<p>x</p>',
            'markdown': '# Hello world',
            'links': {
                'internal': [{'href': '/a', 'text': 'A'}],
                'external': [],
            },
            'metadata': {'description': 'desc'},
            'status_code': 200,
        }
        ps = build_page_structure(probe)
        assert ps.internal_link_count == 1
        assert ps.markdown_chars > 0
        assert ps.internal_link_samples[0].href == '/a'


class TestAgentProbeContract:
    """Planning Agent 应能读到的 JSON 契约"""

    @pytest.fixture
    def probe_json(self):
        controls = extract_page_controls(LOGIN_HTML)
        elements = classify_interactions(LOGIN_HTML, '', controls, PageStructureVo())
        return {
            'page_structure': build_page_structure({'markdown': 'x' * 100, 'links': {}}).model_dump(),
            'controls': [c.model_dump() for c in controls],
            'interactive_elements': [e.model_dump() for e in elements],
            'site_type_candidates': [
                c.model_dump() for c in score_site_types(
                    'http://localhost/app', build_rendering_probe(100, 5000),
                    UrlSignalsVo(), PageStructureVo(), elements,
                )
            ],
        }

    def test_agent_can_find_login_selectors(self, probe_json):
        login = next(e for e in probe_json['interactive_elements'] if e['category'] == 'login_gate')
        assert login['fields']
        assert any(f['role'] == 'password' for f in login['fields'])
        assert login['submit']['selector']

    def test_json_serializable(self, probe_json):
        text = json.dumps(probe_json, ensure_ascii=False)
        loaded = json.loads(text)
        assert 'controls' in loaded
