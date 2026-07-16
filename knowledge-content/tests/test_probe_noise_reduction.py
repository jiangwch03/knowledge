"""探针降噪与版本选择器泛化回归测试"""

from knowledge_content.service.page_probe.category_navigation_detector import detect_category_navigation
from knowledge_content.service.page_probe.interactive_element_classifier import classify_interactive_elements
from knowledge_content.service.page_probe.interaction_classifier import classify_interactions
from knowledge_content.service.page_probe.version_signal_util import (
    detect_version_switcher_signal,
    extract_doc_version_labels,
    is_likely_doc_version_switcher,
)
from knowledge_content.service.vo.page_structure_vo import LinkSampleVo, PageStructureVo

ZHIHU_JSON_NOISE_HTML = """
<script>{"api-v1":"https://x.com","api-v3":"https://y.com","api-v4":"https://z.com"}</script>
<div>职场办公 编程 考试考证 语言学习 兴趣技能 通识</div>
<a href="javascript:void(0)">banner</a>
<p>登录后可查看学习记录哦~</p>
<button>立即登录查看</button>
<input placeholder="搜索你感兴趣的内容..." type="text" />
"""

ZHIHU_VISIBLE = '职场办公 编程 考试考证 语言学习 登录后可查看学习记录 立即登录查看'

DOC_VERSION_HTML = """
<select><option>v3.0.x</option><option>v2.6.x</option></select>
<a href="/docs/v2.6.x/overview">v2.6.x</a>
"""

# 正文很长，版本菜单落在后方（回归：禁止依赖前 N 字符截断）
_LONG_PREFIX = '<main>' + ('Welcome to docs. ' * 1200) + '</main>'


class TestVersionSignalUtil:
    def test_api_version_noise_rejected(self):
        labels = extract_doc_version_labels('api-v1 api-v3 api-v4 v1 v2 v3 v4')
        assert labels == []
        assert not is_likely_doc_version_switcher(['v1', 'v2', 'v3', 'v4'])

    def test_doc_versions_accepted(self):
        labels = extract_doc_version_labels('v3.0.x v2.6.x overview')
        assert len(labels) >= 2
        assert is_likely_doc_version_switcher(labels)


class TestZhihuLikeProbe:
    def test_no_false_version_switcher(self):
        elements = classify_interactive_elements(ZHIHU_JSON_NOISE_HTML, ZHIHU_VISIBLE, 0)
        assert not any(e.category == 'version_switcher' for e in elements)

    def test_login_prompt_detected(self):
        elements = classify_interactive_elements(ZHIHU_JSON_NOISE_HTML, ZHIHU_VISIBLE, 0)
        assert any(e.category == 'login_prompt' for e in elements)

    def test_search_box_from_controls(self):
        from knowledge_content.service.page_probe.control_extractor import extract_page_controls

        controls = extract_page_controls(ZHIHU_JSON_NOISE_HTML)
        elements = classify_interactions(
            ZHIHU_JSON_NOISE_HTML, ZHIHU_VISIBLE, controls, PageStructureVo(),
        )
        assert any(e.category == 'search_box' for e in elements)
        assert not any(e.category == 'filter_panel' for e in elements)

    def test_category_navigation(self):
        ps = PageStructureVo(
            internal_link_count=10,
            internal_link_samples=[
                LinkSampleVo(href='/c1', text='职场办公'),
                LinkSampleVo(href='/c2', text='编程'),
                LinkSampleVo(href='/c3', text='考试考证'),
                LinkSampleVo(href='/c4', text='语言学习'),
            ],
        )
        el = detect_category_navigation(ZHIHU_JSON_NOISE_HTML, ZHIHU_VISIBLE, ps)
        assert el is not None
        assert el.category == 'category_navigation'
        assert len(el.options) >= 3


class TestDocVersionStillWorks:
    def test_version_switcher_on_real_docs(self):
        elements = classify_interactive_elements(DOC_VERSION_HTML, 'v3.0.x v2.6.x', 0)
        assert any(e.category == 'version_switcher' for e in elements)


class TestGeneralizedVersionSwitcher:
    """站点无关结构：native select / ARIA listbox / 链接簇 / 关闭态触发器。"""

    def test_native_select(self):
        html = '<select id="ver"><option>v2.4.0</option><option>v2.5.0</option></select>'
        signal = detect_version_switcher_signal(html, '')
        assert signal is not None
        assert signal.from_select
        assert 'v2.5.0' in signal.options

    def test_aria_listbox_without_brand_class(self):
        """不依赖任何站点 class，只认 role=listbox + 版本文案。"""
        html = _LONG_PREFIX + '''
        <aside>
          <button aria-haspopup="listbox" aria-expanded="false">v1.2.0</button>
          <ul role="listbox" aria-hidden="true">
            <li role="option"><a href="/docs/v1.2.0/">v1.2.0</a></li>
            <li role="option"><a href="/docs/v1.1.0/">v1.1.0</a></li>
            <li role="option"><a href="/docs/v1.0.0/">v1.0.0</a></li>
          </ul>
        </aside>
        '''
        assert len(_LONG_PREFIX) > 15000
        elements = classify_interactive_elements(html, 'Home v1.2.0 Guide', 0)
        ver = next(e for e in elements if e.category == 'version_switcher')
        assert 'v1.1.0' in ver.options
        assert ver.location == 'sidebar'

    def test_docusaurus_like_link_cluster_no_v_prefix(self):
        """Docusaurus 常见：不带 v 的 1.0.0 链接簇。"""
        html = '''
        <nav>
          <ul class="dropdown__menu">
            <li><a href="/docs/2.1.0/intro">2.1.0</a></li>
            <li><a href="/docs/2.0.0/intro">2.0.0</a></li>
            <li><a href="/docs/1.9.0/intro">1.9.0</a></li>
          </ul>
        </nav>
        '''
        signal = detect_version_switcher_signal(html, 'Docs')
        assert signal is not None
        assert signal.from_link_cluster or signal.from_listbox
        assert any(o.startswith('2.') for o in signal.options)

    def test_closed_trigger_only(self):
        """菜单未挂载时：aria-haspopup 触发器文案为版本号即可检出。"""
        html = '<button type="button" aria-haspopup="listbox" aria-expanded="false">v3.0.x</button>'
        elements = classify_interactive_elements(html, 'Home v3.0.x About', 0)
        assert any(e.category == 'version_switcher' for e in elements)

    def test_kubernetes_like_versions_in_menu(self):
        """K8s 文档风格：1.28 / 1.27 无 v 前缀，靠 menu 结构识别。"""
        html = '''
        <div role="menu">
          <a href="/docs/1.28/" role="menuitem">1.28</a>
          <a href="/docs/1.27/" role="menuitem">1.27</a>
          <a href="/docs/1.26/" role="menuitem">1.26</a>
        </div>
        '''
        signal = detect_version_switcher_signal(html, '')
        assert signal is not None
        assert '1.28' in signal.options
        assert '1.27' in signal.options
