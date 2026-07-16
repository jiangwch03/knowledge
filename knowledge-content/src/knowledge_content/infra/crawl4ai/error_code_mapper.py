"""crawl4ai 错误码映射工具

将 crawl4ai 引擎返回的原始错误信息（error_message + status_code）
映射为 CrawlUrlErrorCode 枚举中的细分错误码，供重试策略精准决策。
"""

from knowledge_content.enums.crawl_url_error_code_enum import CrawlUrlErrorCode


# HTTP 状态码 → 错误码映射
# HTTP 状态码 → 错误码映射（常见响应码显式列出，便于排查与重试决策）
_STATUS_CODE_MAPPING: dict[int, str] = {
    # 3xx：最终仍停在重定向
    300: CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    301: CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    302: CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    303: CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    307: CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    308: CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value,
    # 4xx
    400: CrawlUrlErrorCode.CRAWL_FAILED.value,           # Bad Request
    401: CrawlUrlErrorCode.FORBIDDEN_PATH.value,         # Unauthorized
    403: CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value,   # Forbidden（可能为 WAF）
    404: CrawlUrlErrorCode.INVALID_URL.value,            # Not Found
    405: CrawlUrlErrorCode.CRAWL_FAILED.value,           # Method Not Allowed
    408: CrawlUrlErrorCode.PAGE_TIMEOUT.value,           # Request Timeout
    410: CrawlUrlErrorCode.INVALID_URL.value,            # Gone
    429: CrawlUrlErrorCode.RATE_LIMITED.value,           # Too Many Requests
    # 5xx
    500: CrawlUrlErrorCode.SERVICE_HTTP_ERROR.value,     # Internal Server Error
    501: CrawlUrlErrorCode.SERVICE_HTTP_ERROR.value,     # Not Implemented
    502: CrawlUrlErrorCode.CONNECTION_RESET.value,       # Bad Gateway
    503: CrawlUrlErrorCode.CONNECTION_RESET.value,       # Service Unavailable
    504: CrawlUrlErrorCode.PAGE_TIMEOUT.value,           # Gateway Timeout
}

# ---------------------------------------------------------------------------
# 错误消息关键词 → 错误码映射
#
# 【维护规则】
# 1. 列表按顺序遍历，先匹配到的关键词先返回（map_crawl_error_code 步骤2），
#    因此短关键词若放靠前会"吞掉"长关键词——同分类内长关键词排在短关键词之前。
#    例：'navigation timeout' 必须排在 'timeout' 之前，否则只会命中后者。
# 2. 每个分类对应一个 CrawlUrlErrorCode，新增关键词时先确认归属的分类，
#    再追加到该分类末尾；如需新增分类，同步在 crawl_url_error_code_enum.py
#    增加枚举值。
# 3. 关键词统一小写，匹配时已将原始 error_message 转为小写再比较，
#    无需在此处理大小写。
# 4. _STATUS_CODE_MAPPING 的优先级高于本表（步骤1先执行），
#    若某 HTTP 状态码已能精确判定错误码，则无需在此重复添加关键词。
# 5. 末尾兜底返回 CRAWL_FAILED，无需为此添加关键词。
# ---------------------------------------------------------------------------
_KEYWORD_MAPPING: list[tuple[str, str]] = [
    # 浏览器崩溃类 → BROWSER_CRASH（Playwright/Chromium 进程异常终止）
    ('browser crash', CrawlUrlErrorCode.BROWSER_CRASH.value),
    ('browser crashed', CrawlUrlErrorCode.BROWSER_CRASH.value),
    ('browser disconnected', CrawlUrlErrorCode.BROWSER_CRASH.value),
    ('target closed', CrawlUrlErrorCode.BROWSER_CRASH.value),
    ('page crashed', CrawlUrlErrorCode.BROWSER_CRASH.value),

    # 页面加载超时类 → PAGE_TIMEOUT（导航或元素等待超时）
    # 注意：长关键词排前，'timeout' 最后兜底本分类
    ('navigation timeout', CrawlUrlErrorCode.PAGE_TIMEOUT.value),
    ('page load timeout', CrawlUrlErrorCode.PAGE_TIMEOUT.value),
    ('timed out', CrawlUrlErrorCode.PAGE_TIMEOUT.value),
    ('waiting for', CrawlUrlErrorCode.PAGE_TIMEOUT.value),
    ('timeout', CrawlUrlErrorCode.PAGE_TIMEOUT.value),

    # 连接被重置类 → CONNECTION_RESET（网络层中断，含 DNS 解析失败）
    ('connection reset', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('connection refused', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('reset by peer', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('broken pipe', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('econnreset', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('econnrefused', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('network error', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('dns lookup failed', CrawlUrlErrorCode.CONNECTION_RESET.value),
    ('name resolution failed', CrawlUrlErrorCode.CONNECTION_RESET.value),

    # 速率限制类 → RATE_LIMITED（服务端主动限流）
    ('rate limit', CrawlUrlErrorCode.RATE_LIMITED.value),
    ('rate limited', CrawlUrlErrorCode.RATE_LIMITED.value),
    ('too many requests', CrawlUrlErrorCode.RATE_LIMITED.value),
    ('throttled', CrawlUrlErrorCode.RATE_LIMITED.value),

    # Cloudflare 拦截类 → CLOUDFLARE_CHALLENGE（WAF/人机验证/反爬拦截）
    ('cloudflare', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('cf-ray', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('challenge', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('captcha', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('blocked', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('access denied', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('security check', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('ddos protection', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('under attack', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
    ('turnstile', CrawlUrlErrorCode.CLOUDFLARE_CHALLENGE.value),
]


def map_crawl_error_code(error_message: str | None, status_code: int | None) -> str:
    """
    将 crawl4ai 原始错误信息映射为 CrawlUrlErrorCode 细分错误码。

    映射优先级：
    1. HTTP 状态码精确匹配（如 429→RATE_LIMITED、302→UNRESOLVED_REDIRECT）
    2. 状态码区间兜底（其他 3xx / 4xx / 5xx）
    3. 错误消息关键词匹配（如包含 "timeout"→PAGE_TIMEOUT）
    4. 默认返回 CRAWL_FAILED

    :param error_message: crawl4ai 返回的原始错误信息
    :param status_code: HTTP 状态码（若有）
    :return: CrawlUrlErrorCode 枚举值字符串
    """
    # 步骤1：HTTP 状态码精确匹配
    if status_code is not None and status_code in _STATUS_CODE_MAPPING:
        return _STATUS_CODE_MAPPING[status_code]

    # 步骤2：状态码区间兜底
    if status_code is not None:
        code = int(status_code)
        if 300 <= code < 400:
            return CrawlUrlErrorCode.UNRESOLVED_REDIRECT.value
        if code == 404:
            return CrawlUrlErrorCode.INVALID_URL.value
        if 400 <= code < 500:
            return CrawlUrlErrorCode.CRAWL_FAILED.value
        if 500 <= code < 600:
            return CrawlUrlErrorCode.SERVICE_HTTP_ERROR.value

    # 步骤3：错误消息关键词匹配
    if error_message:
        msg_lower = error_message.lower()
        for keyword, error_code in _KEYWORD_MAPPING:
            if keyword in msg_lower:
                return error_code

    # 步骤4：默认返回 CRAWL_FAILED
    return CrawlUrlErrorCode.CRAWL_FAILED.value


def is_successful_http_status(status_code: int | None) -> bool:
    """None 不因状态码判失败；有值时仅 2xx 视为成功。"""
    if status_code is None:
        return True
    return 200 <= int(status_code) < 300


def _has_usable_content(content: str | None) -> bool:
    return bool(content and str(content).strip())


def apply_http_status_gate(
    *,
    success: bool,
    status_code: int | None,
    error_message: str | None = None,
    redirected_url: str | None = None,
    content: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    crawl4ai 结果出口：校正 success。

    引擎标 success 但最终 HTTP 非 2xx（如 302）→ 失败。
    例外：3xx 且已有 redirected_url，同时正文非空 → 视为重定向已跟进，放行。
    :return: (success, error_code, error_message)
    """
    if success and is_successful_http_status(status_code):
        return True, None, None

    if success and not is_successful_http_status(status_code):
        code = int(status_code) if status_code is not None else None
        if (
            code is not None
            and 300 <= code < 400
            and redirected_url
            and _has_usable_content(content)
        ):
            return True, None, None
        msg = f'HTTP {status_code}：最终响应非 2xx'
        return False, map_crawl_error_code(msg, status_code), msg

    msg = error_message or 'Unknown error'
    return False, map_crawl_error_code(msg, status_code), msg
