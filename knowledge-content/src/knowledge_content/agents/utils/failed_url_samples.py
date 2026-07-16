"""
失败修复样本 URL：从任务 URL 记录 / error_message 抽取失败页。

crawl_retry 要求：对本任务「任意一个」失败 URL + 新配置试爬成功即可
（第 1 个或第 99 个都行）；禁止仅用入口页过门禁；不要求修通全部失败页。
"""

from __future__ import annotations

import re
from collections import Counter

from knowledge_content.enums.crawl_url_error_code_enum import CrawlUrlErrorCode
from knowledge_content.mapper.dao.web_crawler_task_url_record_dao import (
    WebCrawlerTaskUrlRecordDao,
)

# 内容/加载类失败优先排在前面（仅影响提示文案顺序，不影响门禁 OR 范围）
_CONTENT_FIX_ERROR_CODES = frozenset({
    CrawlUrlErrorCode.EMPTY_CONTENT.value,
    CrawlUrlErrorCode.PAGE_TIMEOUT.value,
    CrawlUrlErrorCode.CRAWL_FAILED.value,
    CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value,
    CrawlUrlErrorCode.RATE_LIMITED.value,
})

_ERROR_MESSAGE_URL_RE = re.compile(
    r'(https?://[^\s\[\];，,]+)',
    re.IGNORECASE,
)

# 拒绝文案里举例的失败页数量（实际校验覆盖全部失败 URL）
FAILED_URL_HINT_COUNT = 3


def parse_failed_urls_from_error_message(error_message: str | None) -> list[str]:
    """从任务级 error_message 文本解析失败 URL（保序去重）。"""
    if not error_message:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for match in _ERROR_MESSAGE_URL_RE.finditer(error_message):
        url = match.group(1).rstrip(').,;；')
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


async def resolve_all_failed_urls(
    task_id: int,
    *,
    error_message: str | None = None,
) -> list[str]:
    """
    解析本任务全部失败 URL（保序去重），供门禁 OR 校验。

    优先主因错误码（内容类、出现次数多）排前，便于拒绝文案举例；
    校验时对列表内任一 URL 的试爬凭证均接受。
    """
    records = await WebCrawlerTaskUrlRecordDao.get_failed_records_by_task_id(task_id)

    by_code: dict[str, list[str]] = {}
    seen: set[str] = set()
    for record in records:
        url = (getattr(record, 'url', None) or '').strip()
        if not url or url in seen:
            continue
        seen.add(url)
        code = (getattr(record, 'error_code', None) or '').strip() or 'UNKNOWN'
        by_code.setdefault(code, []).append(url)

    code_counts = Counter({code: len(urls) for code, urls in by_code.items()})
    preferred_codes = sorted(
        code_counts.keys(),
        key=lambda c: (
            0 if c in _CONTENT_FIX_ERROR_CODES else 1,
            -code_counts[c],
            c,
        ),
    )

    urls: list[str] = []
    for code in preferred_codes:
        for url in by_code[code]:
            if url not in urls:
                urls.append(url)

    for url in parse_failed_urls_from_error_message(error_message):
        if url not in seen:
            seen.add(url)
            urls.append(url)

    return urls


def hint_failed_urls(urls: list[str], *, limit: int = FAILED_URL_HINT_COUNT) -> list[str]:
    """拒绝文案用的举例子集。"""
    return list(urls[: max(0, limit)])


# 兼容旧名：现返回全部失败 URL（门禁 OR）
async def resolve_failed_url_samples(
    task_id: int,
    *,
    error_message: str | None = None,
    max_samples: int | None = None,
) -> list[str]:
    """
    解析失败修复须认可的 URL 集合。

    :param max_samples: 已废弃；保留参数以免旧调用报错，忽略并返回全部失败 URL
    """
    _ = max_samples
    return await resolve_all_failed_urls(task_id, error_message=error_message)
