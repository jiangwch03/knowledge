"""
网页爬取 Agent 分析工具 - 单页面抓取与分析

薄适配层：定义 LangGraph 工具接口，复杂解析逻辑下沉到 WebCrawlerAnalysisService
"""
import json

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService


@tool
async def fetch_page(url: str) -> str:
    """
    抓取目标页面并分析页面结构特征。

    输入目标URL，返回包含以下信息的JSON字符串：
    - title: 页面标题
    - has_js_rendering: 是否需要JS渲染
    - has_pagination: 是否有分页
    - pagination_type: 分页类型（page/scroll/load_more/none）
    - has_popup: 是否有弹窗
    - popup_type: 弹窗类型（cookie/login/subscribe/none）
    - content_structure: 内容结构概述
    - internal_link_count: 内链数量
    - external_link_count: 外链数量

    Args:
        url: 目标页面URL
    """
    try:
        vo = await WebCrawlerAnalysisService.fetch_page(url)
        return vo.model_dump_json(by_alias=True, ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[Analysis] fetch_page 异常: {}', err)
        return f'Error: {err}'


if __name__ == "__main__":
    import asyncio

    async def main():
        # 测试URL，可根据需要修改
        test_url = "https://milvus.io/docs/zh"
        result = await WebCrawlerAnalysisService.fetch_page(test_url)
        print(result)

    asyncio.run(main())
