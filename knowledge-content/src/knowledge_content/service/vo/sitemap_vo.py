"""sitemap.xml 解析结果 VO（服务层）"""

from pydantic import BaseModel


class SitemapVo(BaseModel):
    """
    sitemap.xml 解析结果 VO

    由 WebCrawlerAnalysisService.fetch_sitemap 返回，
    对目标站点的 sitemap.xml 进行结构化解析，供上层业务（Agent 工具）消费。
    """

    # 是否存在 sitemap.xml
    has_sitemap: bool
    # URL 总量
    total_urls: int = 0
    # 按路径前缀分组的计数
    url_groups: dict[str, int] = {}
    # 抽样代表性 URL（最多10个）
    sample_urls: list[str] = []
