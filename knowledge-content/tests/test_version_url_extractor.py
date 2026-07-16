"""版本 URL 提取与探针事实提取测试"""

from knowledge_content.service.page_probe.probe_action_planner import extract_version_url_facts
from knowledge_content.service.page_probe.version_url_extractor import extract_version_url_patterns
from knowledge_content.service.page_probe.url_signals_analyzer import analyze_url_signals
from knowledge_content.service.trial_quality_gate_service import TrialQualityGateService


SAMPLE_HTML = """
<a href="/docs/zh/v2.6.x/overview.md">v2.6.x</a>
<a href="/docs/v2.6.x/overview.md">v2.6.x</a>
<a href="/docs/overview.md">v3.0.x</a>
<a href="/docs/zh/overview.md">首页</a>
"""

MILVUS_NAV_MD = """[首页](https://milvus.io/docs/zh/v2.6.x)
v2.6.x
  * [v3.0.x](https://milvus.io/docs/overview.md)
  * [v2.6.x](https://milvus.io/docs/v2.6.x/overview.md)
## 什么是 Milvus
正文内容"""


class TestVersionUrlExtractor:
    def test_extract_patterns(self):
        patterns = extract_version_url_patterns('https://milvus.io/docs/zh', SAMPLE_HTML)
        labels = {p.version_label for p in patterns}
        assert 'v2.6.x' in labels or any('2.6' in label for label in labels)

    def test_extract_version_url_facts(self):
        url_signals = analyze_url_signals('https://milvus.io/docs/zh')
        patterns = extract_version_url_facts(
            'https://milvus.io/docs/zh', SAMPLE_HTML, url_signals,
        )
        assert len(patterns) >= 1
        assert any('2.6' in p.url_prefix for p in patterns)


class TestVersionMismatchFix:
    def test_v26_direct_url_not_mismatch(self):
        gate = TrialQualityGateService.evaluate(
            success=True,
            title='',
            markdown=MILVUS_NAV_MD + '\n' + ('x' * 500),
            status_code=200,
            expected_version='v2.6.x',
        )
        assert 'VERSION_MISMATCH' not in gate.issues
