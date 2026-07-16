"""将 crawl4ai CrawlResult / probe_page 字典适配为 PageStructureVo"""

from __future__ import annotations

import re
from typing import Any

from knowledge_content.service.vo.page_structure_vo import LinkSampleVo, PageStructureVo


def _markdown_text(raw: Any) -> str:
    """从 CrawlResult.markdown（对象或字符串）取纯文本长度计算用"""
    if raw is None:
        return ''
    if isinstance(raw, str):
        return raw
    return getattr(raw, 'raw_markdown', None) or str(raw)


def build_page_structure(probe_result: dict) -> PageStructureVo:
    """
    ① 结构化探针底座：把 crawl4ai 单次 arun 结果转为 PageStructureVo。

    :param probe_result: Crawl4aiClient.probe_page 返回的 dict
    """
    links = probe_result.get('links') or {}
    internal = links.get('internal') or []
    external = links.get('external') or []
    metadata = probe_result.get('metadata') or {}
    media = probe_result.get('media') or {}
    images = media.get('images') or []
    tables = probe_result.get('tables') or []

    samples: list[LinkSampleVo] = []
    for item in internal[:15]:
        if isinstance(item, dict):
            samples.append(LinkSampleVo(
                href=item.get('href', '') or '',
                text=(item.get('text') or '')[:120],
            ))
        elif isinstance(item, str):
            samples.append(LinkSampleVo(href=item, text=''))

    markdown = probe_result.get('markdown') or ''
    if not markdown and probe_result.get('visible_text'):
        markdown = probe_result['visible_text']

    title = probe_result.get('title') or metadata.get('title') or ''

    return PageStructureVo(
        title=title[:300],
        description=(metadata.get('description') or '')[:500],
        markdown_chars=len(_markdown_text(markdown)),
        html_chars=len(probe_result.get('html') or ''),
        internal_link_count=len(internal),
        external_link_count=len(external),
        internal_link_samples=samples,
        table_count=len(tables) if isinstance(tables, list) else 0,
        image_count=len(images) if isinstance(images, list) else 0,
        status_code=probe_result.get('status_code'),
        redirected_url=probe_result.get('redirected_url'),
    )


def visible_text_from_html(html: str) -> str:
    """从 HTML 提取可见文本（probe 兜底）"""
    if not html:
        return ''
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()
