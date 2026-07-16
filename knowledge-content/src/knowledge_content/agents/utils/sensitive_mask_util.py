"""会话消息敏感信息脱敏（落库前）"""

import re

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'(password\s*[:=]\s*)\S+', re.I), r'\1***'),
    (re.compile(r'(passwd\s*[:=]\s*)\S+', re.I), r'\1***'),
    (re.compile(r'(authorization\s*[:=]\s*Bearer\s+)\S+', re.I), r'\1***'),
    (re.compile(r'(Bearer\s+)\S+', re.I), r'\1***'),
    (re.compile(r'(Cookie\s*[:=]\s*)([^;\n]{8,})', re.I), r'\1***'),
    (re.compile(r'(token\s*[:=]\s*)\S+', re.I), r'\1***'),
    (re.compile(r'(api[_-]?key\s*[:=]\s*)\S+', re.I), r'\1***'),
]


def mask_sensitive_text(text: str) -> str:
    """对密码/Cookie/Token 等做简单掩码，降低落库泄露风险"""
    if not text:
        return text
    masked = text
    for pattern, repl in _PATTERNS:
        masked = pattern.sub(repl, masked)
    return masked
