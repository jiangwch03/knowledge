"""
爬取失败诊断摘要

给 Agent / 任务 error_message 提供可调参的证据：长度、状态码、重定向、正文预览，
并在「HTML 有字 / Markdown 几乎空」时给出明确检查方向。
"""

from __future__ import annotations

from typing import Any


_PREVIEW_LIMIT = 120


def content_preview(text: str | None, *, limit: int = _PREVIEW_LIMIT) -> str:
    """截取正文预览（压缩空白）。"""
    if not text:
        return ''
    compact = ' '.join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + '…'


def build_crawl_diagnostics(
    *,
    content_length: int = 0,
    html_length: int | None = None,
    status_code: int | None = None,
    redirected_url: str | None = None,
    title: str | None = None,
    markdown: str | None = None,
    requested_url: str | None = None,
    final_url: str | None = None,
) -> dict[str, Any]:
    """构造统一诊断 dict（供 trial_crawl / query 复用）。"""
    preview = content_preview(markdown)
    diag: dict[str, Any] = {
        'content_length': int(content_length or 0),
        'html_length': html_length,
        'status_code': status_code,
        'redirected_url': (redirected_url or '').strip() or None,
        'title': (title or '').strip() or None,
        'content_preview': preview or None,
        'extraction_hint': _extraction_hint(
            content_length=int(content_length or 0),
            html_length=html_length,
        ),
    }
    req = (requested_url or '').strip() or None
    fin = (final_url or '').strip() or None
    if req:
        diag['requested_url'] = req
    if fin and fin != req:
        diag['final_url'] = fin
    return diag


def format_empty_content_message(
    *,
    content_length: int = 0,
    html_length: int | None = None,
    status_code: int | None = None,
    redirected_url: str | None = None,
    title: str | None = None,
    markdown: str | None = None,
    requested_url: str | None = None,
    final_url: str | None = None,
) -> str:
    """
    EMPTY_CONTENT 可读错误文案（写入 URL 记录 / 任务摘要）。

    例：页面正文为空（content_length=1, html_length=8200, status_code=200,
    redirected_url=https://...）；HTML有内容但Markdown几乎为空，优先检查...
    """
    diag = build_crawl_diagnostics(
        content_length=content_length,
        html_length=html_length,
        status_code=status_code,
        redirected_url=redirected_url,
        title=title,
        markdown=markdown,
        requested_url=requested_url,
        final_url=final_url,
    )
    parts: list[str] = [f'content_length={diag["content_length"]}']
    if diag.get('html_length') is not None:
        parts.append(f'html_length={diag["html_length"]}')
    if diag.get('status_code') is not None:
        parts.append(f'status_code={diag["status_code"]}')
    if diag.get('redirected_url'):
        parts.append(f'redirected_url={diag["redirected_url"]}')
    if diag.get('final_url') and diag.get('final_url') != diag.get('redirected_url'):
        parts.append(f'final_url={diag["final_url"]}')
    if diag.get('title'):
        parts.append(f'title={diag["title"]}')

    msg = f'页面正文为空（{", ".join(parts)}）'
    hint = diag.get('extraction_hint')
    if hint:
        msg = f'{msg}；{hint}'
    preview = diag.get('content_preview')
    if preview:
        msg = f'{msg}；preview={preview}'
    return msg


def diagnostics_from_crawl_result(result: Any, *, requested_url: str | None = None) -> dict[str, Any]:
    """从 CrawlResultVo（或兼容对象）提取诊断。"""
    markdown = getattr(result, 'markdown', None) or ''
    return build_crawl_diagnostics(
        content_length=len(markdown),
        html_length=getattr(result, 'html_length', None),
        status_code=getattr(result, 'status_code', None),
        redirected_url=getattr(result, 'redirected_url', None),
        title=getattr(result, 'title', None),
        markdown=markdown,
        requested_url=requested_url,
        final_url=getattr(result, 'url', None),
    )


def _extraction_hint(*, content_length: int, html_length: int | None) -> str | None:
    """根据 HTML vs Markdown 长度差给出调参方向。"""
    html_len = int(html_length) if html_length is not None else None
    if content_length < 50 and html_len is not None and html_len > 500:
        return (
            'HTML有内容但Markdown几乎为空，优先检查 css_selector / content_filter'
            '（如 PruningContentFilter）/ wait_for，勿只加 page_timeout'
        )
    if content_length < 50 and html_len is not None and html_len < 200:
        return 'HTML也几乎为空，更可能是页面未渲染完成或被重定向到空壳页，检查 wait_until / hooks / 最终URL'
    if content_length < 50:
        return '正文过短，结合 status_code 与 redirected_url 判断是提取失败还是加载失败'
    return None
