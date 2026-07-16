"""爬取失败诊断文案与 EMPTY_CONTENT 格式化。"""

from knowledge_content.service.crawl_failure_diagnostics import (
    build_crawl_diagnostics,
    content_preview,
    format_empty_content_message,
)


def test_content_preview_truncates():
    text = 'a' * 200
    preview = content_preview(text, limit=20)
    assert len(preview) == 20
    assert preview.endswith('…')


def test_format_empty_content_html_rich_markdown_empty():
    msg = format_empty_content_message(
        content_length=1,
        html_length=8200,
        status_code=200,
        redirected_url='https://milvus.io/docs/milvus-webui.md',
        title='',
        markdown='-',
        requested_url='https://milvus.io/docs/zh/milvus-webui.md',
        final_url='https://milvus.io/docs/zh/milvus-webui.md',
    )
    assert 'content_length=1' in msg
    assert 'html_length=8200' in msg
    assert 'status_code=200' in msg
    assert 'redirected_url=' in msg
    assert 'css_selector' in msg
    assert 'content_filter' in msg


def test_format_empty_content_html_also_empty():
    msg = format_empty_content_message(
        content_length=0,
        html_length=10,
        status_code=302,
    )
    assert 'HTML也几乎为空' in msg
    assert 'status_code=302' in msg


def test_build_crawl_diagnostics_keys():
    diag = build_crawl_diagnostics(
        content_length=1,
        html_length=5000,
        status_code=200,
        markdown='x',
    )
    assert diag['content_length'] == 1
    assert diag['html_length'] == 5000
    assert diag['extraction_hint']
    assert 'css_selector' in diag['extraction_hint']
