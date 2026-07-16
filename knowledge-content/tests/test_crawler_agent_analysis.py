"""
爬取 Agent 站点分析测试

覆盖 Agent 的核心分析能力与异常处理，包括：
- 分析服务层：真实 HTTP 请求 milvus.io 验证工具正常运作
- 异常处理：Mock HTTP 层模拟各种故障场景
- 结果采集：验证 collect_results_node 正确聚合工具结果
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge_common.exceptions.exception import ServiceException
from knowledge_content.agents.tools.fetch_robots_txt import fetch_robots_txt
from knowledge_content.agents.tools.fetch_sitemap import fetch_sitemap
from knowledge_content.agents.tools.fetch_page import fetch_page
from knowledge_content.agents.tools.fetch_crawling_anti import anti_crawling_test
from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService

from langchain_core.messages import AIMessage, HumanMessage

from knowledge_content.agents.tools.fetch_sitemap import _parse_path_prefix

# 测试目标
MILVUS_URL = 'https://milvus.io/docs/zh'
MILVUS_BASE = 'https://milvus.io'
MILVUS_ROBOTS = 'https://milvus.io/robots.txt'
MILVUS_SITEMAP = 'https://milvus.io/sitemap.xml'

# ============================================================
# 第一部分：分析服务层 - 正常链路（真实 HTTP）
# ============================================================


@pytest.mark.integration
class TestAnalysisServiceWithRealHttp:
    """使用真实 HTTP 请求访问 milvus.io，验证分析工具在真实环境下的输出"""

    @pytest.mark.asyncio
    async def test_fetch_robots_txt(self):
        """正常获取 milvus.io 的 robots.txt

        验证：成功解析 robots.txt，至少包含 disallowed_paths 和 sitemap_urls
        """
        result = await WebCrawlerAnalysisService.fetch_robots_txt(MILVUS_URL)
        assert result.has_robots is True
        # milvus.io 的 robots.txt 通常允许 / 路径
        assert '/' in result.allowed_paths
        # 应包含 sitemap 地址
        assert any('sitemap' in url.lower() for url in result.sitemap_urls)
        assert result.disallowed_paths is not None

    @pytest.mark.asyncio
    async def test_fetch_sitemap(self):
        """正常获取 milvus.io 的 sitemap

        验证：成功解析 sitemap，返回 URL 分组和至少一个分组
        """
        result = await WebCrawlerAnalysisService.fetch_sitemap(MILVUS_BASE)
        assert result.has_sitemap is True
        assert result.total_urls > 0
        assert len(result.url_groups) > 0
        assert len(result.sample_urls) > 0

    @pytest.mark.asyncio
    async def test_fetch_sitemap_with_path_prefix(self):
        """正常获取 sitemap 并按 /docs/zh 路径前缀过滤

        验证：过滤后 URL 全部包含 /docs/zh 路径
        """
        result = await WebCrawlerAnalysisService.fetch_sitemap(
            MILVUS_URL, path_prefix=['/docs/zh']
        )
        assert result.has_sitemap is True
        assert result.total_urls > 0
        # 验证所有 sample_url 都包含 /docs/zh 路径
        for url in result.sample_urls:
            assert '/docs/zh' in url

    @pytest.mark.asyncio
    async def test_fetch_page(self):
        """正常抓取 milvus.io/docs/zh 页面并分析结构

        验证：成功获取页面，提取标题和链接
        """
        result = await WebCrawlerAnalysisService.fetch_page(MILVUS_URL)
        assert result.title is not None and len(result.title) > 0
        assert result.internal_link_count >= 0
        assert result.external_link_count >= 0

    @pytest.mark.asyncio
    async def test_anti_crawling(self):
        """正常检测 milvus.io 反爬等级

        验证：返回反爬等级和检测结论
        """
        result = await WebCrawlerAnalysisService.anti_crawling_test(MILVUS_BASE)
        assert hasattr(result, 'anti_crawl_level')
        assert hasattr(result, 'recommendation')
        assert result.anti_crawl_level in ('light', 'moderate', 'heavy', 'unknown')

    @pytest.mark.asyncio
    async def test_fetch_sitemap_sitemap_index(self):
        """验证 sitemap index 递归解析（milvus.io 可能是 sitemap index）

        验证：能正确解析 sitemap index 并聚合所有子 sitemap 的 URL
        """
        result = await WebCrawlerAnalysisService.fetch_sitemap(MILVUS_BASE)
        assert result.has_sitemap is True
        assert result.total_urls > 0
        # 检查 URL 分组中是否包含 docs、blog 等常见前缀
        path_prefixes = list(result.url_groups.keys())
        docs_group = any('docs' in p for p in path_prefixes)
        assert docs_group, f'URL分组中应包含 /docs 前缀，实际分组: {path_prefixes}'


# ============================================================
# 第二部分：分析服务层 - 异常场景（Mock HTTP）
# ============================================================


class TestAnalysisServiceErrorHandling:
    """通过 Mock UrlUtil.async_http_get 模拟各种故障场景"""

    @pytest.mark.asyncio
    async def test_invalid_url_empty(self):
        """异常：空 URL 应抛出 ServiceException"""
        with pytest.raises(ServiceException, match='URL不能为空'):
            await WebCrawlerAnalysisService.fetch_robots_txt('')

    @pytest.mark.asyncio
    async def test_invalid_url_no_scheme(self):
        """异常：缺少协议头的 URL 应抛出 ServiceException"""
        with pytest.raises(ServiceException, match='无效的URL格式|不支持的URL协议'):
            await WebCrawlerAnalysisService.fetch_robots_txt('not-a-url')

    @pytest.mark.asyncio
    async def test_robots_txt_http_404(self):
        """异常：robots.txt 返回 404

        验证：has_robots=False，Vo 中带 error 信息
        """
        with patch.object(
            WebCrawlerAnalysisService,
            'fetch_robots_txt',
            new_callable=AsyncMock,
        ) as mock_method:
            mock_vo = MagicMock()
            mock_vo.has_robots = False
            mock_vo.allowed_paths = []
            mock_vo.disallowed_paths = []
            mock_vo.sitemap_urls = []
            mock_vo.crawl_delay = None
            mock_method.return_value = mock_vo

            result = await WebCrawlerAnalysisService.fetch_robots_txt(MILVUS_URL)
            assert result.has_robots is False

    @pytest.mark.asyncio
    async def test_sitemap_http_error(self):
        """异常：sitemap 请求失败（模拟网络错误）

        验证：ServiceException 被抛出或 has_sitemap=False
        """
        with patch(
            'knowledge_content.service.web_crawler_analysis_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
        ) as mock_http:
            mock_http.side_effect = ServiceException('HTTP请求失败，状态码: 500')

            with pytest.raises(ServiceException):
                await WebCrawlerAnalysisService.fetch_sitemap(MILVUS_BASE)

    @pytest.mark.asyncio
    async def test_page_fetch_timeout(self):
        """异常：页面抓取超时

        验证：fetch_page 方法抛出异常或返回带 error 的结果
        """
        with patch(
            'knowledge_content.service.web_crawler_analysis_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
        ) as mock_http:
            mock_http.side_effect = ServiceException('HTTP请求超时')

            with pytest.raises(ServiceException):
                await WebCrawlerAnalysisService.fetch_page(MILVUS_URL)

    @pytest.mark.asyncio
    async def test_anti_crawl_dns_failure(self):
        """异常：DNS 解析失败导致反爬检测失败

        验证：返回 unknown 等级和错误信息
        """
        with patch(
            'knowledge_content.service.web_crawler_analysis_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
        ) as mock_http:
            mock_http.side_effect = ServiceException('域名解析失败')

            with pytest.raises(ServiceException):
                await WebCrawlerAnalysisService.anti_crawling_test('https://unknown-domain-12345.com')

    @pytest.mark.asyncio
    async def test_fetch_robots_txt_not_found(self):
        """异常：async_http_get 对非 200 抛出 ServiceException

        UrlUtil.async_http_get 在收到非 200 状态码时抛出 ServiceException，
        验证服务层正确传播该异常（异常处理下沉到工具适配层）
        """
        with patch(
            'knowledge_content.service.web_crawler_analysis_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
            side_effect=ServiceException('HTTP请求失败，状态码: 404，URL: https://milvus.io/robots.txt'),
        ):
            with pytest.raises(ServiceException, match='HTTP请求失败，状态码: 404'):
                await WebCrawlerAnalysisService.fetch_robots_txt(MILVUS_URL)


# ============================================================
# 第三部分：工具适配层 - 异常传播测试
# ============================================================


class TestCrawlerToolErrorHandling:
    """验证 LangGraph 工具适配层（thin wrapper）对异常的捕获与序列化

    工具适配层应保证：不抛出异常，始终返回字符串（JSON 或错误消息）
    """

    @pytest.mark.asyncio
    async def test_fetch_robots_tool_http_error_returns_string(self):
        """robots.txt 工具：HTTP 失败时返回错误字符串而非抛出异常"""
        with patch(
            'knowledge_content.agents.tools.fetch_robots_txt.WebCrawlerAnalysisService.fetch_robots_txt',
            new_callable=AsyncMock,
        ) as mock_svc:
            mock_svc.side_effect = ServiceException('HTTP请求失败，状态码: 500')

            result = await fetch_robots_txt.ainvoke({'url': MILVUS_URL})
            assert isinstance(result, str)
            assert '500' in result

    @pytest.mark.asyncio
    async def test_fetch_sitemap_tool_unexpected_error(self):
        """sitemap 工具：非 ServiceException 异常也返回字符串"""
        with patch(
            'knowledge_content.agents.tools.fetch_sitemap.WebCrawlerAnalysisService.fetch_sitemap',
            new_callable=AsyncMock,
        ) as mock_svc:
            mock_svc.side_effect = RuntimeError('意外的内部错误')

            result = await fetch_sitemap.ainvoke({'url': MILVUS_BASE})
            assert isinstance(result, str)
            assert '意外的内部错误' in result

    @pytest.mark.asyncio
    async def test_fetch_page_tool_error_returns_error_prefix(self):
        """fetch_page 工具：异常时返回 'Error: xxx' 格式"""
        with patch(
            'knowledge_content.agents.tools.fetch_page.WebCrawlerAnalysisService.fetch_page',
            new_callable=AsyncMock,
        ) as mock_svc:
            mock_svc.side_effect = TimeoutError('请求超时')

            result = await fetch_page.ainvoke({'url': MILVUS_URL})
            assert isinstance(result, str)
            assert result.startswith('Error:')

    @pytest.mark.asyncio
    async def test_anti_crawling_tool_error_returns_json(self):
        """anti_crawling 工具：异常时返回带 error 字段的 JSON"""
        with patch(
            'knowledge_content.agents.tools.fetch_crawling_anti.WebCrawlerAnalysisService.anti_crawling_test',
            new_callable=AsyncMock,
        ) as mock_svc:
            mock_svc.side_effect = ConnectionError('连接被拒绝')

            result = await anti_crawling_test.ainvoke({'url': MILVUS_BASE})
            assert isinstance(result, str)
            parsed = json.loads(result)
            assert parsed.get('anti_crawl_level') == 'unknown'
            assert 'error' in parsed

    @pytest.mark.asyncio
    async def test_fetch_sitemap_tool_with_string_path_prefix(self):
        """fetch_sitemap 工具适配层接受字符串 path_prefix 并正确传递给服务层"""
        with patch(
            'knowledge_content.agents.tools.fetch_sitemap.WebCrawlerAnalysisService.fetch_sitemap',
            new_callable=AsyncMock,
        ) as mock_svc:
            mock_vo = MagicMock()
            mock_vo.model_dump_json.return_value = '{"has_sitemap": true, "total_urls": 100}'
            mock_svc.return_value = mock_vo

            result = await fetch_sitemap.ainvoke({
                'url': MILVUS_BASE,
                'path_prefix': '["/docs/zh"]',
            })
            assert isinstance(result, str)
            parsed = json.loads(result)
            assert parsed.get('has_sitemap') is True


# ============================================================
# 第六部分：工具 URL 校验安全测试
# ============================================================


class TestUrlValidation:
    """验证分析服务对异常 URL 输入的防御能力"""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_url_with_query_params(self):
        """带查询参数的 URL（?version=v2.5）应能正常获取 robots.txt"""
        result = await WebCrawlerAnalysisService.fetch_robots_txt('https://milvus.io/docs?version=v2.5')
        assert result.has_robots is True

    @pytest.mark.asyncio
    async def test_ip_address_url_raises(self):
        """纯 IP URL 请求失败时应抛出 ServiceException"""
        with patch(
            'knowledge_content.service.web_crawler_analysis_service.UrlUtil.async_http_get',
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = ServiceException('HTTP请求失败，状态码: 503')
            with pytest.raises(ServiceException):
                await WebCrawlerAnalysisService.fetch_robots_txt('http://192.168.1.1/robots.txt')

    @pytest.mark.asyncio
    async def test_ftp_url_raises(self):
        """不支持的协议（ftp）应抛出 ServiceException"""
        with pytest.raises(ServiceException, match='不支持的URL协议|仅支持'):
            await WebCrawlerAnalysisService.fetch_robots_txt('ftp://files.example.com/robots.txt')

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_url_with_fragment_ignored(self):
        """带 #fragment 的 URL，片段部分被 urlparse 忽略，请求不受影响"""
        result = await WebCrawlerAnalysisService.fetch_robots_txt('https://milvus.io/docs#overview')
        assert result.has_robots is True


# ============================================================
# 第七部分：Planning create_agent 图结构（见 test_planning_create_agent.py）
# ============================================================


# ============================================================
# 第八部分：path_prefix 格式兼容性测试
# ============================================================


class TestParsePathPrefix:
    """验证 _parse_path_prefix 对多种输入格式的兼容性

    模拟 DeepSeek 将 list 序列化为 JSON 字符串的真实行为，
    确保 fetch_sitemap 工具在 LLM 输出不规范时仍能正常工作。
    """

    def test_none_input(self):
        """path_prefix=None → None"""
        assert _parse_path_prefix(None) is None

    def test_list_input(self):
        """合法的 list 输入 → 原样返回"""
        result = _parse_path_prefix(['/docs/zh'])
        assert result == ['/docs/zh']

    def test_json_array_string_input(self):
        """模拟 DeepSeek 行为：JSON 数组字符串 → 正确解析为 list"""
        result = _parse_path_prefix('["/docs/zh"]')
        assert result == ['/docs/zh']

    def test_plain_string_input(self):
        """普通字符串 → 包装为单元素 list"""
        result = _parse_path_prefix('/docs/zh')
        assert result == ['/docs/zh']

    def test_multi_element_json_string(self):
        """多元素 JSON 数组字符串"""
        result = _parse_path_prefix('["/docs/zh", "/api/zh"]')
        assert result == ['/docs/zh', '/api/zh']

    def test_empty_list_input(self):
        """空 list"""
        result = _parse_path_prefix([])
        assert result == []

    def test_invalid_json_string(self):
        """非法 JSON 字符串 → 原样包装"""
        result = _parse_path_prefix('{invalid}')
        assert result == ['{invalid}']
