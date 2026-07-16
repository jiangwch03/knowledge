"""渲染探测结果 VO"""

from pydantic import BaseModel, Field


class RenderingProbeVo(BaseModel):
    """HTTP 与浏览器渲染内容对比"""

    mode: str = 'unknown'  # static | ssr | spa | hybrid | unknown
    http_body_chars: int = 0  # HTTP 快探响应体字符数
    rendered_body_chars: int = 0  # 浏览器渲染后可见正文字符数
    content_ratio: float = 0.0  # rendered / http 比值，用于判定 SPA/空壳
    shell_risk: str = 'unknown'  # low | medium | high
    needs_browser: bool = False  # 是否建议后续爬取走浏览器渲染
    browser_probe_ok: bool = True  # crawl4ai 浏览器探针是否成功
    browser_probe_error: str | None = None  # 浏览器探针失败原因
