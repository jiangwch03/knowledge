"""敏感信息脱敏测试"""

from knowledge_content.agents.utils.sensitive_mask_util import mask_sensitive_text


def test_mask_password():
    text = 'username=admin password=Secret123!'
    assert 'Secret123' not in mask_sensitive_text(text)
    assert 'password=***' in mask_sensitive_text(text)


def test_mask_bearer():
    text = 'Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.xxx'
    masked = mask_sensitive_text(text)
    assert 'eyJhbGci' not in masked


def test_mask_cookie():
    text = 'Cookie: session=abc123def456; Path=/'
    masked = mask_sensitive_text(text)
    assert 'abc123def456' not in masked
