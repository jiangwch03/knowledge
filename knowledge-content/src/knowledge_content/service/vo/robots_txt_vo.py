"""robots.txt 解析结果 VO（服务层）"""

from pydantic import BaseModel


class RobotsTxtVo(BaseModel):
    """
    robots.txt 解析结果 VO

    由 WebCrawlerAnalysisService.fetch_robots_txt 返回，
    对目标站点的 robots.txt 进行结构化解析，供上层业务（Agent 工具）消费。
    """

    # 是否存在 robots.txt
    has_robots: bool
    # robots.txt 解析失败时的错误信息
    error: str | None = None
    # 允许爬取的路径列表
    allowed_paths: list[str] = []
    # 禁止爬取的路径列表
    disallowed_paths: list[str] = []
    # Sitemap 地址列表
    sitemap_urls: list[str] = []
    # 爬取延迟（秒）
    crawl_delay: int | None = None
