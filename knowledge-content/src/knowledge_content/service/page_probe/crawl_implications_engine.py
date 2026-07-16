"""根据探针结果推导爬取策略含义（站点无关规则，供 Agent 快速索引）"""

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.rendering_probe_vo import RenderingProbeVo
from knowledge_content.service.vo.suggested_crawl_action_vo import VersionUrlPatternVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo


def derive_crawl_implications(
    rendering: RenderingProbeVo,
    url_signals: UrlSignalsVo,
    interactive_elements: list[InteractiveElementVo],
    version_url_patterns: list[VersionUrlPatternVo] | None = None,
) -> list[str]:
    """
    从探针结构化结果推导 crawl_implications 短标签。

    细节在 interactive_elements / controls / page_structure；此处仅作 Agent 速览索引。
    """
    implications: list[str] = []
    patterns = version_url_patterns or []
    categories = {el.category for el in interactive_elements}

    if not rendering.browser_probe_ok:
        implications.append('browser_probe_failed')
    if rendering.needs_browser or rendering.shell_risk == 'high':
        implications.append('needs_browser_rendering')
    if rendering.shell_risk == 'high':
        implications.append('shell_risk_high')

    version_el = _find_by_category(interactive_elements, 'version_switcher')
    if version_el and version_el.confidence >= 0.7 and not url_signals.has_version_in_path:
        implications.append('version_not_in_url_ask_user')
        implications.append('needs_browser_for_version_discovery')
    if patterns:
        implications.append('version_url_patterns_discovered')

    if 'language_switcher' in categories:
        implications.append('confirm_target_language')

    login_el = _find_by_category(interactive_elements, 'login_gate')
    if login_el:
        implications.append('ask_user_for_credentials')
        if login_el.fields:
            implications.append('login_form_fields_detected')

    if 'login_prompt' in categories:
        implications.append('ask_user_for_credentials')
        implications.append('login_required_for_full_content')

    if 'category_navigation' in categories:
        implications.append('category_navigation_detected')
        implications.append('ask_user_for_crawl_scope')

    if 'search_box' in categories:
        implications.append('site_search_available')

    pagination_el = _find_by_category(interactive_elements, 'pagination')
    if pagination_el:
        implications.append(f'pagination_{pagination_el.mode or "detected"}')

    if 'filter_panel' in categories:
        filter_el = _find_by_category(interactive_elements, 'filter_panel')
        if filter_el and (filter_el.filters or filter_el.confidence >= 0.6):
            implications.append('list_page_with_filters')

    if 'captcha' in categories:
        implications.append('blocked_without_captcha')
    if 'tab_panel' in categories or 'expandable_section' in categories:
        implications.append('may_need_expand_hook')
    if 'sidebar_navigation' in categories and rendering.mode in ('spa', 'hybrid'):
        implications.append('do_not_trust_http_link_count')
    if 'client_side_router' in categories:
        implications.append('client_side_routing_detected')

    return list(dict.fromkeys(implications))


def _find_by_category(
    elements: list[InteractiveElementVo],
    category: str,
) -> InteractiveElementVo | None:
    for el in elements:
        if el.category == category:
            return el
    return None
