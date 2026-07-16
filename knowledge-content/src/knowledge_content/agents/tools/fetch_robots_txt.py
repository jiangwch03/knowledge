"""
网页爬取 Agent 分析工具 - robots.txt 获取与解析

薄适配层：定义 LangGraph 工具接口，复杂解析逻辑下沉到 WebCrawlerAnalysisService
"""

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.url_util import get_base_url
from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService
from knowledge_content.service.vo.robots_txt_vo import RobotsTxtVo


@tool
async def fetch_robots_txt(url: str) -> str:
    """
    获取目标站点的 robots.txt 并解析为结构化结论。

    输入目标URL，返回包含以下信息的JSON字符串：
    - allowed_paths: 允许爬取的路径列表
    - disallowed_paths: 禁止爬取的路径列表
    - sitemap_urls: Sitemap 地址列表
    - crawl_delay: 爬取延迟（秒）
    - has_robots: 是否存在 robots.txt

    Args:
        url: 目标站点URL
    """
    try:
        base_url = get_base_url(url)
        result: RobotsTxtVo = await WebCrawlerAnalysisService.fetch_robots_txt(base_url)
        return result.model_dump_json(ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[Analysis] fetch_robots_txt 异常: {}', err)
        return err



if __name__ == "__main__":
    import asyncio

    async def main():
        # 测试URL，可根据需要修改
        test_url = "https://milvus.io/docs/zh"
        result = await WebCrawlerAnalysisService.fetch_robots_txt(test_url)
        print(result)

    asyncio.run(main())
