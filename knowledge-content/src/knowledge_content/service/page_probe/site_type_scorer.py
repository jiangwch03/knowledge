"""
④ 站点类型打分：对齐 prompts.yaml 八种站点类型，输出候选与依据。

探针只打分，不替 Agent 定 site_type。
"""

from __future__ import annotations

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.page_structure_vo import PageStructureVo
from knowledge_content.service.vo.rendering_probe_vo import RenderingProbeVo
from knowledge_content.service.vo.site_type_candidate_vo import SiteTypeCandidateVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo

# prompts.yaml「三、站点类型识别说明」八种类型
_SITE_TYPES = (
    '技术文档站',
    '新闻/博客站',
    '电商/产品站',
    'SPA 应用',
    'Wiki/知识库',
    '政府/机构站',
    'API 文档站',
    '社交/论坛',
)


def score_site_types(
    url: str,
    rendering: RenderingProbeVo,
    url_signals: UrlSignalsVo,
    page_structure: PageStructureVo,
    interactive_elements: list[InteractiveElementVo],
) -> list[SiteTypeCandidateVo]:
    """根据多路信号为各站点类型打分，返回按 score 降序的候选列表"""
    categories = {e.category for e in interactive_elements}
    scores: dict[str, tuple[float, list[str]]] = {t: (0.0, []) for t in _SITE_TYPES}

    def add(site_type: str, points: float, signal: str) -> None:
        s, sigs = scores[site_type]
        scores[site_type] = (s + points, sigs + [signal])

    url_lower = url.lower()

    # 技术文档站
    if '/docs' in url_lower or '/documentation' in url_lower:
        add('技术文档站', 0.35, 'URL 含 /docs/')
    if 'version_switcher' in categories:
        ver = next((e for e in interactive_elements if e.category == 'version_switcher'), None)
        if ver and ver.confidence >= 0.7:
            add('技术文档站', 0.25, '有文档版本选择器')
    if 'sidebar_navigation' in categories:
        add('技术文档站', 0.15, '侧边栏导航密集')
    if url_signals.has_language_in_path:
        add('技术文档站', 0.1, 'URL 含语言段')

    # SPA 应用
    if rendering.mode in ('spa', 'hybrid'):
        add('SPA 应用', 0.3, f'rendering.mode={rendering.mode}')
    if 'client_side_router' in categories:
        add('SPA 应用', 0.25, '客户端路由链接多')
    if rendering.needs_browser:
        add('SPA 应用', 0.1, 'needs_browser')

    # API 文档站
    if 'tab_panel' in categories:
        add('API 文档站', 0.3, '存在 Tab 结构')
    if '/api' in url_lower or 'swagger' in url_lower or 'redoc' in url_lower:
        add('API 文档站', 0.35, 'URL 含 API 文档特征')

    # 新闻/博客站 / 课程平台
    if 'pagination' in categories:
        add('新闻/博客站', 0.2, '有分页/加载更多')
    if any(k in url_lower for k in ('/blog', '/news', '/article')):
        add('新闻/博客站', 0.3, 'URL 含 blog/news')
    if any(k in url_lower for k in ('/education', '/learning', '/course')):
        add('新闻/博客站', 0.25, 'URL 含 education/learning/course')
    if 'category_navigation' in categories:
        add('新闻/博客站', 0.2, '有分类/频道导航')

    # 电商/产品站
    if 'filter_panel' in categories:
        add('电商/产品站', 0.25, '有筛选面板')
    if 'login_gate' in categories and 'filter_panel' in categories:
        add('电商/产品站', 0.2, '登录门+筛选（后台/商城常见）')

    # Wiki
    if page_structure.internal_link_count > 80:
        add('Wiki/知识库', 0.25, f'内链密集({page_structure.internal_link_count})')
    if '/wiki' in url_lower:
        add('Wiki/知识库', 0.35, 'URL 含 wiki')

    # 政府/机构站
    if any(k in url_lower for k in ('.gov', '.edu.cn', '政府')):
        add('政府/机构站', 0.4, '政府/机构域名或路径')
    if rendering.mode == 'static' and not rendering.needs_browser:
        add('政府/机构站', 0.15, '偏静态 SSR')

    # 社交/论坛
    if 'login_gate' in categories and 'captcha' in categories:
        add('社交/论坛', 0.25, '登录+验证码')
    if 'pagination' in categories and rendering.mode == 'spa':
        add('社交/论坛', 0.15, 'SPA+feed 分页特征')

    # 登录门对电商/后台/SaaS 的加权
    if 'login_gate' in categories:
        add('电商/产品站', 0.15, '需登录访问')
        add('SPA 应用', 0.15, '需登录的 SPA/后台')

    candidates = [
        SiteTypeCandidateVo(site_type=t, score=round(s, 2), signals=sigs)
        for t, (s, sigs) in scores.items()
        if s > 0.1
    ]
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:5]
