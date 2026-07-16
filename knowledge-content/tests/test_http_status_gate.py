"""crawl4ai HTTP 状态码门禁单测"""

from knowledge_content.enums.crawl_url_error_code_enum import CrawlUrlErrorCode
from knowledge_content.infra.crawl4ai.error_code_mapper import (
    apply_http_status_gate,
    is_successful_http_status,
    map_crawl_error_code,
)


def test_2xx_ok_302_not():
    assert is_successful_http_status(None)
    assert is_successful_http_status(200)
    assert not is_successful_http_status(302)


def test_apply_http_status_gate_rejects_302_success():
    ok, code, msg = apply_http_status_gate(success=True, status_code=302)
    assert ok is False
    assert code == CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value
    assert '302' in (msg or '')


def test_apply_http_status_gate_salvages_302_with_redirect_and_content():
    ok, code, msg = apply_http_status_gate(
        success=True,
        status_code=302,
        redirected_url='https://milvus.io/docs/zh/overview',
        content='# Overview\n\n真实正文内容',
    )
    assert ok is True
    assert code is None
    assert msg is None


def test_apply_http_status_gate_rejects_302_without_content():
    ok, code, msg = apply_http_status_gate(
        success=True,
        status_code=302,
        redirected_url='https://milvus.io/docs/zh/overview',
        content='  ',
    )
    assert ok is False
    assert code == CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value


def test_apply_http_status_gate_rejects_302_without_redirected_url():
    ok, code, _ = apply_http_status_gate(
        success=True,
        status_code=302,
        content='# has body but no redirected_url',
    )
    assert ok is False


def test_apply_http_status_gate_keeps_200():
    ok, code, msg = apply_http_status_gate(success=True, status_code=200)
    assert ok is True
    assert code is None
    assert msg is None


def test_map_302():
    assert map_crawl_error_code(None, 302) == CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value


def test_map_404():
    assert map_crawl_error_code(None, 404) == CrawlUrlErrorCode.INVALID_URL.value
