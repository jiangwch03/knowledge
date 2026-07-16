"""
URL 工具函数

提供 URL 提取和 base URL 比较功能，供 url_router_node 和 service 层共用。
"""

import re
from urllib.parse import urlparse

from knowledge_common.exceptions.exception import ServiceException

_URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')


def extract_url(content: str) -> str:
    """从消息文本中提取第一个 URL"""

    if content is None or content == '':
        return ''

    match = _URL_PATTERN.search(content)
    return match.group(0) if match else ''


def get_base_url(url: str) -> str:
    """提取 URL 的 scheme://netloc（如 https://example.com）"""

    if url is None or not url.startswith('http'):
        raise ServiceException(f'URL 非法 {url}')

    parsed = urlparse(url)
    return f'{parsed.scheme}://{parsed.netloc}' if parsed.netloc else ''
