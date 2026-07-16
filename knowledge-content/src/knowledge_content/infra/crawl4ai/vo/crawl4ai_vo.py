"""crawl4ai 爬取结果 VO"""

from pydantic import BaseModel


class CrawlResultVo(BaseModel):
    """
    单次爬取结果 VO

    封装 crawl4ai 引擎返回的爬取结果，屏蔽底层 SDK 细节。
    成功时填充 url / markdown / title / media / links，失败时填充 url / status_code / error_code / error_message。
    仅在 infra 层内部和后处理器输入中使用，上层业务代码不直接消费。
    """

    # 是否爬取成功
    success: bool
    # 爬取的目标 URL
    url: str
    # 爬取成功时的 Markdown 内容
    markdown: str | None = None
    # 爬取成功时的页面标题
    title: str | None = None
    # HTTP 状态码（有响应时）
    status_code: int | None = None
    # 最终跳转 URL（若有重定向）；失败诊断用，不入库原文字段
    redirected_url: str | None = None
    # 原始 HTML 长度（不保留全文，仅供 EMPTY_CONTENT 诊断）
    html_length: int | None = None
    # 提取的媒体资源（images/videos/audios 的 URL 列表）
    media: dict | None = None
    # 提取的链接（internal/external URL 列表）
    links: dict | None = None
    # 爬取失败时的错误码
    error_code: str | None = None
    # 爬取失败时的错误信息
    error_message: str | None = None
