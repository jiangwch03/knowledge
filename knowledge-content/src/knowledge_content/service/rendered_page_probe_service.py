"""渲染探针主服务：HTTP 快探 + crawl4ai 结构化浏览器探针 + 交互归类"""

import httpx

from knowledge_common.utils.log_util import logger
from knowledge_common.utils.url_util import UrlUtil
from knowledge_content.infra.crawl4ai.crawl4ai_client import Crawl4aiClient
from knowledge_content.service.page_probe.control_extractor import extract_page_controls
from knowledge_content.service.page_probe.crawl4ai_probe_adapter import (
    build_page_structure,
    visible_text_from_html,
)
from knowledge_content.service.page_probe.crawl_implications_engine import derive_crawl_implications
from knowledge_content.service.page_probe.interaction_classifier import classify_interactions
from knowledge_content.service.page_probe.probe_action_planner import extract_version_url_facts
from knowledge_content.service.page_probe.rendering_analyzer import (
    build_rendering_probe,
    refine_rendering_for_interactions,
)
from knowledge_content.service.page_probe.probe_access_guard import (
    apply_probe_block_short_circuit,
    detect_probe_block,
)
from knowledge_content.service.page_probe.probe_crawl_config import build_probe_crawl_config
from knowledge_content.service.page_probe.site_type_scorer import score_site_types
from knowledge_content.service.page_probe.url_signals_analyzer import analyze_url_signals
from knowledge_content.service.vo.rendered_page_probe_vo import RenderedPageProbeVo


def _count_nav_links(html: str) -> int:
    import re
    nav_blocks = re.findall(
        r'<(?:nav|aside)[^>]*>(.*?)</(?:nav|aside)>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    count = 0
    for block in nav_blocks:
        count += len(re.findall(r'<a\s', block, re.IGNORECASE))
    return count


class RenderedPageProbeService:
    """
    双通道页面渲染探针（五层流水线编排）。

    ① page_structure  ← crawl4ai 结构化 arun
    ② controls          ← DOM 控件提取
    ③ interactive_elements ← 交互语义归类
    ④ site_type_candidates ← 站点类型打分
    ⑤ version_url_patterns ← 版本 URL 事实（非策略）
    """

    @classmethod
    async def probe(
        cls,
        url: str,
        *,
        hooks: dict | None = None,
        cookies: str | None = None,
    ) -> RenderedPageProbeVo:
        UrlUtil.validate_and_parse_url(url)
        url_signals = analyze_url_signals(url)
        probe_crawl_config = build_probe_crawl_config(hooks=hooks, cookies=cookies)
        auth_injected = bool(probe_crawl_config)

        # HTTP 快探（与浏览器对比用）
        http_body_chars = 0
        http_error: str | None = None
        try:
            response = await UrlUtil.async_http_get(
                url, httpx.Response, headers={'User-Agent': 'Mozilla/5.0'},
            )
            http_body_chars = len(response.text or '')
        except Exception as e:
            http_error = str(e)
            logger.opt(exception=True).warning('[RenderedPageProbe] HTTP 快探失败: url={}, error={}', url, e)

        browser_probe_ok = True
        browser_probe_error: str | None = http_error
        browser_result: dict = {}

        try:
            browser_result = await Crawl4aiClient.probe_page(url, probe_crawl_config)
            browser_probe_ok = bool(browser_result.get('success'))
            if browser_probe_ok:
                browser_probe_error = None
            else:
                browser_probe_error = browser_result.get('error') or '浏览器探针失败'
        except Exception as e:
            browser_probe_ok = False
            browser_probe_error = str(e)
            logger.opt(exception=True).warning('[RenderedPageProbe] 浏览器探针失败: url={}, error={}', url, e)

        # ① 结构化底座
        page_structure = build_page_structure(browser_result) if browser_result else build_page_structure({})
        rendered_html = browser_result.get('html') or ''
        rendered_text = browser_result.get('visible_text') or visible_text_from_html(rendered_html)
        if page_structure.markdown_chars > 0 and not rendered_text:
            rendered_text = browser_result.get('markdown') or ''

        rendered_body_chars = page_structure.markdown_chars or len(rendered_text)
        rendering = build_rendering_probe(
            http_body_chars,
            rendered_body_chars,
            browser_probe_ok=browser_probe_ok,
            browser_probe_error=browser_probe_error,
        )

        # ② 控件提取
        controls = extract_page_controls(rendered_html) if rendered_html else []

        # ③ 交互归类
        nav_link_count = _count_nav_links(rendered_html)
        interactive_elements = []
        if rendered_html or rendered_text or controls:
            interactive_elements = classify_interactions(
                rendered_html,
                rendered_text,
                controls,
                page_structure,
                nav_link_count,
            )

        rendering = refine_rendering_for_interactions(
            rendering, url_signals, interactive_elements,
        )

        # ⑤ 版本 URL 事实（不含 suggested_actions）
        version_url_patterns = []
        if rendered_html:
            version_url_patterns = extract_version_url_facts(
                url, rendered_html, url_signals,
            )

        implications = derive_crawl_implications(
            rendering, url_signals, interactive_elements,
            version_url_patterns=version_url_patterns,
        )

        # ④ 站点类型打分
        site_type_candidates = score_site_types(
            url, rendering, url_signals, page_structure, interactive_elements,
        )

        title = page_structure.title or browser_result.get('title') or ''
        actual_url = page_structure.redirected_url or url

        vo = RenderedPageProbeVo(
            url=url,
            title=title[:200],
            rendering=rendering,
            url_signals=url_signals,
            page_structure=page_structure,
            controls=controls,
            interactive_elements=interactive_elements,
            version_url_patterns=version_url_patterns,
            site_type_candidates=site_type_candidates,
            crawl_implications=implications,
            error=browser_probe_error if not browser_probe_ok and not rendered_text else None,
            actual_url=actual_url,
        )

        block_reason, intended_url = detect_probe_block(
            url,
            actual_url,
            interactive_elements,
            auth_injected=auth_injected,
        )
        if block_reason:
            vo = vo.model_copy(update={
                'block_reason': block_reason,
                'intended_url': intended_url,
            })
            return apply_probe_block_short_circuit(vo)

        return vo
