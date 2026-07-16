"""estimate_total_pages / _extract_max_pages 路径兼容性"""

import pytest

from knowledge_content.service.web_crawler_analysis_service import WebCrawlerAnalysisService


class TestExtractMaxPages:
    def test_agent_nested_crawler_run_config(self):
        config = {
            'browser_config': {'headless': True},
            'crawler_run_config': {
                'deep_crawl_strategy': {
                    'crawl_strategy': 'BFSDeepCrawlStrategy',
                    'max_depth': 3,
                    'max_pages': 200,
                    'filter_chain': {
                        'include_patterns': ['https://milvus.io/docs/zh/*'],
                        'exclude_patterns': ['*/login'],
                    },
                },
            },
        }
        assert WebCrawlerAnalysisService._extract_max_pages(config) == 200

    def test_flat_deep_crawl_strategy(self):
        config = {
            'deep_crawl_strategy': {
                'max_pages': 50,
            },
        }
        assert WebCrawlerAnalysisService._extract_max_pages(config) == 50

    def test_serialized_params(self):
        config = {
            'crawler_run_config': {
                'deep_crawl_strategy': {
                    'type': 'BFSDeepCrawlStrategy',
                    'params': {'max_pages': 80},
                },
            },
        }
        assert WebCrawlerAnalysisService._extract_max_pages(config) == 80

    def test_null_max_pages_returns_zero(self):
        config = {
            'crawler_run_config': {
                'deep_crawl_strategy': {'max_pages': None},
            },
        }
        assert WebCrawlerAnalysisService._extract_max_pages(config) == 0

    def test_missing_returns_zero(self):
        assert WebCrawlerAnalysisService._extract_max_pages({}) == 0
        assert WebCrawlerAnalysisService._extract_max_pages(None) == 0


class TestEstimateTotalPages:
    @pytest.mark.asyncio
    async def test_nested_config_with_exclude_discount(self):
        config = {
            'crawler_run_config': {
                'deep_crawl_strategy': {
                    'max_pages': 100,
                    'filter_chain': {'exclude_patterns': ['*/admin']},
                },
            },
        }
        result = await WebCrawlerAnalysisService.estimate_total_pages(
            'https://milvus.io/zh', config,
        )
        assert result == 80  # 100 * 0.8

    @pytest.mark.asyncio
    async def test_regression_agent_format_was_zero_before_fix(self):
        """回归：Agent 标准嵌套结构此前会被误读为 0"""
        config = {
            'crawler_run_config': {
                'deep_crawl_strategy': {
                    'max_pages': 200,
                    'filter_chain': {'include_patterns': ['https://milvus.io/docs/zh/*']},
                },
            },
        }
        result = await WebCrawlerAnalysisService.estimate_total_pages(
            'https://milvus.io/zh', config,
        )
        assert result == 200
