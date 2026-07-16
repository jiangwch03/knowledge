"""
网页爬取 Agent 分析工具 - sitemap 获取与解析

薄适配层：定义 LangGraph 工具接口，复杂解析逻辑下沉到 WebCrawlerAnalysisService
"""

from urllib.parse import urlparse

from langchain_core.tools import tool

from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.url_util import get_base_url
from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService
from knowledge_content.service.vo.sitemap_vo import SitemapVo


def _parse_path_prefix(path_prefix: str | list[str] | None) -> list[str] | None:
    """兼容多种 path_prefix 输入格式，统一返回 list[str] | None"""
    if path_prefix is None:
        return None
    if isinstance(path_prefix, list):
        return path_prefix
    # 字符串格式：尝试 JSON 数组解析，否则当单个前缀
    stripped = path_prefix.strip()
    if stripped.startswith('[') and stripped.endswith(']'):
        import json as _json
        try:
            return _json.loads(stripped)
        except _json.JSONDecodeError:
            return [stripped]
    return [stripped]


def _derive_path_prefix_from_url(url: str) -> list[str] | None:
    """当未显式传 path_prefix 时，从 URL 路径自动推导范围前缀。"""
    parsed = urlparse(url)
    scope_path = parsed.path.strip()
    if not scope_path or scope_path == '/':
        return None
    normalized = f'/{scope_path.lstrip("/")}'
    return [normalized]


@tool
async def fetch_sitemap(url: str, path_prefix: str | None = None) -> str:
    """
    获取目标站点的 sitemap.xml 并统计URL分布。

    支持按多个路径前缀过滤，当用户URL携带多个范围路径时（如 /docs/zh, /api/zh），
    传入这些路径作为 path_prefix 参数（JSON 数组字符串），只统计匹配这些前缀的URL，使抽样更聚焦。

    输入目标URL，返回包含以下信息的JSON字符串：
    - total_urls: URL 总量
    - url_groups: 按路径前缀分组的计数（如 /docs/: 150, /blog/: 80）
    - sample_urls: 抽样代表性URL（最多10个）
    - has_sitemap: 是否存在 sitemap.xml

    Args:
        url: 目标站点URL
        path_prefix: 可选，路径前缀（JSON 数组字符串，如 '["/docs/zh", "/api/zh"]' 或 "/docs/zh"），只统计匹配这些前缀的URL
    """
    try:
        base_url = get_base_url(url)
        parsed_prefix = _parse_path_prefix(path_prefix) or _derive_path_prefix_from_url(url)
        result: SitemapVo = await WebCrawlerAnalysisService.fetch_sitemap(base_url, parsed_prefix)
        return result.model_dump_json(ensure_ascii=False)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[Analysis] fetch_sitemap 异常: {}', err)
        return err


if __name__ == "__main__":
    import asyncio

    async def main():
        # 测试URL，可根据需要修改
        test_url = "https://milvus.io"
        result = await WebCrawlerAnalysisService.fetch_sitemap(test_url)
        print(result.model_dump_json(ensure_ascii=False))

    asyncio.run(main())
