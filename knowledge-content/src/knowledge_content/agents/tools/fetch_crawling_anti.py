"""
网页爬取 Agent 分析工具 - 反爬机制检测

薄适配层：定义 LangGraph 工具接口，复杂解析逻辑下沉到 WebCrawlerAnalysisService
"""
import json

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.vo.anti_crawl_vo import AntiCrawlVo
from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService


@tool
async def anti_crawling_test(url: str) -> str:
    """
    检测目标站点的反爬机制等级。

    输入目标URL，返回包含以下信息的JSON字符串：
    - anti_crawl_level: 反爬等级（light/moderate/heavy）
    - needs_js_rendering: 是否需要JS渲染
    - has_captcha: 是否有验证码
    - has_rate_limiting: 是否有请求限速
    - has_cloudflare: 是否有Cloudflare保护
    - detected_headers: 检测到的特殊请求头
    - recommendation: 反爬应对建议

    Args:
        url: 目标站点URL
    """
    try:
        result:AntiCrawlVo = await WebCrawlerAnalysisService.anti_crawling_test(url)
        return result.model_dump_json(ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[Analysis] test_anti_crawling 异常: {}', err)
        return json.dumps({'anti_crawl_level': 'unknown', 'error': err}, ensure_ascii=False)


if __name__ == "__main__":
    import asyncio

    async def main():
        # 测试URL，可根据需要修改
        test_url = "https://milvus.io/docs/zh"
        result = await WebCrawlerAnalysisService.anti_crawling_test(test_url)
        print(result)

    asyncio.run(main())
