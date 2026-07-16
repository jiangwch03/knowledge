"""反爬机制检测结果 VO（服务层）"""

from pydantic import BaseModel


class AntiCrawlVo(BaseModel):
    """
    反爬机制检测结果 VO

    由 WebCrawlerAnalysisService.test_anti_crawling 返回，
    对目标站点的反爬机制进行多维度检测与分级，供上层业务（Agent 工具）消费。
    """

    # 反爬等级（light / moderate / heavy）
    anti_crawl_level: str = 'light'
    # 是否需要 JS 渲染
    needs_js_rendering: bool = False
    # 是否有验证码
    has_captcha: bool = False
    # 是否有频率限制
    has_rate_limiting: bool = False
    # 是否有 Cloudflare 防护
    has_cloudflare: bool = False
    # 检测到的响应头列表（最多10个）
    detected_headers: list[str] = []
    # 爬取建议
    recommendation: str = ''
