"""
crawl4ai SDK 模式实现

通过进程内直接调用 crawl4ai Python 库执行爬取，适用于单机部署或开发环境。
本模块为内部实现，由 Crawl4aiClient 门面统一调度，业务层不应直接引用。
"""

from collections.abc import AsyncIterator
from inspect import signature

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.config.env import Crawl4aiConfig
from knowledge_common.utils.log_util import logger
from knowledge_content.infra.crawl4ai._crawl4ai_config_builder import Crawl4aiConfigBuilder
from knowledge_content.infra.crawl4ai.error_code_mapper import apply_http_status_gate
from knowledge_content.infra.crawl4ai.vo.crawl4ai_vo import CrawlResultVo

# CrawlerRunConfig 是普通 Python 类（非 Pydantic），参数仅在 __init__ 中定义
# 预提取签名参数集合，用于校验用户策略 key 是否合法
_CRAWLER_RUN_CONFIG_PARAMS = set(signature(CrawlerRunConfig.__init__).parameters.keys()) - {'self'}


class _Crawl4aiSdkClient:
    """crawl4ai SDK 模式内部实现"""

    @classmethod
    async def crawl(cls, target_url: str, crawl_config: dict | None = None) -> list[CrawlResultVo]:
        """
        通过本地 SDK 执行爬取

        :param target_url: 目标 URL
        :param crawl_config: 用户策略配置
        :return: 爬取结果列表
        :raises ServiceException: crawl4ai 未安装时抛出
        """
        # 1. 构建浏览器配置
        browser_config = cls._build_browser_config()

        # 2. 构建运行配置（固定默认 + 用户策略合并）
        run_config = cls._build_run_config(crawl_config)

        # 3. 执行爬取
        return await cls._do_crawl(target_url, browser_config, run_config)

    @classmethod
    async def crawl_stream(cls, target_url: str, crawl_config: dict | None = None) -> AsyncIterator[CrawlResultVo]:
        """
        流式爬取，每爬完一个页面立即 yield 结果，避免全量结果驻留内存

        :param target_url: 目标 URL
        :param crawl_config: 用户策略配置
        :return: 异步生成器，逐个产出 CrawlResultVo
        """
        browser_config = cls._build_browser_config()
        # 强制 stream=True，由 async_generator 逐个产出结果，而非全量收集
        run_config = cls._build_run_config(crawl_config, stream=True)

        async for result in cls._do_crawl_stream(target_url, browser_config, run_config):
            yield result

    @classmethod
    async def _do_crawl_stream(
        cls,
        target_url: str,
        browser_config: BrowserConfig,
        run_config: CrawlerRunConfig,
    ) -> AsyncIterator[CrawlResultVo]:
        """流式爬取内部实现，逐个 yield 爬取结果"""
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                crawl_output = await crawler.arun(url=target_url, config=run_config)
                # stream=True 时 arun 返回 async_generator，逐个 yield
                async for result in crawl_output:
                    yield cls._to_crawl_result_vo(target_url, result)

        except ImportError:
            logger.error('[Crawl4aiSdkClient] crawl4ai 未安装')
            raise ServiceException(message='crawl4ai 未安装，请执行 pip install crawl4ai')
        except Exception as e:
            logger.exception('[Crawl4aiSdkClient] 流式爬取异常: {}', e)
            yield CrawlResultVo(
                success=False,
                url=target_url,
                error_code='CRAWL4AI_ERROR',
                error_message=str(e),
            )

    @classmethod
    async def probe_page(cls, target_url: str, crawl_config: dict | None = None) -> dict:
        """
        ① 结构化探针底座：crawl4ai 单次 arun，返回链接/元数据/正文量等事实。

        供 RenderedPageProbeService 消费；不解读业务，不做 hooks 策略。
        """
        import re

        run_config = cls._build_run_config(
            cls._merge_probe_crawl_config(crawl_config),
            stream=False,
        )
        try:
            async with AsyncWebCrawler(config=cls._build_browser_config()) as crawler:
                crawl_output = await crawler.arun(url=target_url, config=run_config)
                result = crawl_output
                if run_config.stream:
                    async for item in crawl_output:
                        result = item
                        break

                if result and result.success:
                    html = getattr(result, 'html', '') or getattr(result, 'cleaned_html', '') or ''
                    md_raw = getattr(result, 'markdown', None)
                    markdown = ''
                    if md_raw is not None:
                        markdown = getattr(md_raw, 'raw_markdown', None) or str(md_raw)
                    visible_text = ''
                    if html:
                        visible_text = re.sub(r'<[^>]+>', ' ', html)
                        visible_text = re.sub(r'\s+', ' ', visible_text).strip()
                    elif markdown:
                        visible_text = re.sub(r'\s+', ' ', markdown).strip()
                    metadata = getattr(result, 'metadata', None) or {}
                    return {
                        'success': True,
                        'title': getattr(result, 'title', '') or metadata.get('title', '') or '',
                        'html': html,
                        'visible_text': visible_text,
                        'markdown': markdown,
                        'links': getattr(result, 'links', None) or {},
                        'metadata': metadata if isinstance(metadata, dict) else {},
                        'media': getattr(result, 'media', None) or {},
                        'tables': getattr(result, 'tables', None) or [],
                        'status_code': getattr(result, 'status_code', None),
                        'redirected_url': getattr(result, 'redirected_url', None),
                        'error': None,
                    }
                error_message = result.error_message if result else 'Unknown error'
                return {
                    'success': False,
                    'title': '',
                    'html': '',
                    'visible_text': '',
                    'markdown': '',
                    'links': {},
                    'metadata': {},
                    'media': {},
                    'tables': [],
                    'status_code': getattr(result, 'status_code', None) if result else None,
                    'redirected_url': None,
                    'error': error_message,
                }
        except ImportError:
            return {
                'success': False,
                'title': '',
                'html': '',
                'visible_text': '',
                'markdown': '',
                'links': {},
                'metadata': {},
                'error': 'crawl4ai 未安装',
            }
        except Exception as e:
            logger.exception('[Crawl4aiSdkClient] probe_page 异常: {}', e)
            return {
                'success': False,
                'title': '',
                'html': '',
                'visible_text': '',
                'markdown': '',
                'links': {},
                'metadata': {},
                'error': str(e),
            }

    @classmethod
    def _merge_probe_crawl_config(cls, crawl_config: dict | None) -> dict:
        """探针默认参数 + 可选 hooks / crawler_run_config"""
        from knowledge_content.agents.utils.strategy_config_resolver import (
            merge_hook_params,
            resolve_strategy_config,
        )

        probe_defaults = {
            'cache_mode': 'BYPASS',
            'page_timeout': 30000,
            'wait_until': 'domcontentloaded',
            'word_count_threshold': 0,
            'stream': False,
        }
        if not crawl_config:
            return probe_defaults
        _, crawler_run_config, hooks = resolve_strategy_config(crawl_config)
        merged = {**probe_defaults, **crawler_run_config}
        return merge_hook_params(merged, hooks)

    @classmethod
    def _build_browser_config(cls) -> BrowserConfig:
        """构建浏览器配置，所有固定默认参数统一由 Crawl4aiConfig 管理"""
        return BrowserConfig(
            headless=Crawl4aiConfig.crawl4ai_headless,              # 无头浏览器，生产环境固定开启
            user_agent=Crawl4aiConfig.crawl4ai_user_agent,          # 通用桌面 UA，降低被识别为爬虫的概率
            viewport_width=Crawl4aiConfig.crawl4ai_viewport_width,  # 标准桌面视口宽度，避免移动端布局
            viewport_height=Crawl4aiConfig.crawl4ai_viewport_height,# 标准桌面视口高度
            enable_stealth=Crawl4aiConfig.crawl4ai_enable_stealth,  # 基础反爬防御（隐藏自动化特征），无副作用
            verbose=Crawl4aiConfig.crawl4ai_verbose,                # 内部日志开关，生产环境关闭保持日志干净
            proxy_config=None,                                      # 代理配置，默认无代理
        )

    @classmethod
    def _build_run_config(cls, crawl_config: dict | None, stream: bool | None = None) -> CrawlerRunConfig:
        """构建运行配置，固定默认参数作为基础，用户策略可覆盖"""
        run_config_params: dict = {
            'cache_mode': CacheMode.ENABLED,                             # 缓存固定开启，避免重复请求
            'excluded_tags': Crawl4aiConfig.crawl4ai_excluded_tags,      # 排除噪音标签
            'only_text': Crawl4aiConfig.crawl4ai_only_text,              # 保留结构化输出
            'word_count_threshold': Crawl4aiConfig.crawl4ai_word_count_threshold,  # 过滤零碎内容块
            'stream': stream if stream is not None else Crawl4aiConfig.crawl4ai_stream,  # 流式返回结果
        }
        # 合并用户策略配置（LLM 生成或用户手动调整）：仅接受 CrawlerRunConfig.__init__ 支持的参数，忽略未知键
        if crawl_config:
            # 先通过 ConfigBuilder 将声明式 JSON dict 转换为 Python 对象（如 markdown_generator → DefaultMarkdownGenerator 实例）
            built_config = Crawl4aiConfigBuilder.build_crawl_config(crawl_config)
            for key, value in built_config.items():
                if key in _CRAWLER_RUN_CONFIG_PARAMS:
                    run_config_params[key] = value
                else:
                    logger.warning(f'[Crawl4aiSdkClient] 忽略未知策略参数: {key}')

        return CrawlerRunConfig(**run_config_params)

    @classmethod
    async def _do_crawl(
        cls,
        target_url: str,
        browser_config: BrowserConfig,
        run_config: CrawlerRunConfig,
    ) -> list[CrawlResultVo]:
        """
        调用 crawl4ai 引擎执行实际爬取

        兼容 stream=True（async generator）和 stream=False（单结果）两种返回模式。
        """
        try:
            results: list[CrawlResultVo] = []
            async with AsyncWebCrawler(config=browser_config) as crawler:
                crawl_output = await crawler.arun(url=target_url, config=run_config)

                # stream=True 时 arun 返回 async_generator，需逐个获取结果
                if run_config.stream:
                    async for result in crawl_output:
                        results.append(cls._to_crawl_result_vo(target_url, result))
                else:
                    results.append(cls._to_crawl_result_vo(target_url, crawl_output))

            return results

        except ImportError:
            logger.error('[Crawl4aiSdkClient] crawl4ai 未安装')
            raise ServiceException(message='crawl4ai 未安装，请执行 pip install crawl4ai')
        except Exception as e:
            logger.exception('[Crawl4aiSdkClient] 执行异常: {}', e)
            return [CrawlResultVo(
                success=False,
                url=target_url,
                error_code='CRAWL4AI_ERROR',
                error_message=str(e),
            )]

    @classmethod
    def _to_crawl_result_vo(cls, target_url: str, result) -> CrawlResultVo:
        """将 crawl4ai 原始 CrawlResult 转换为 CrawlResultVo"""
        status_code = getattr(result, 'status_code', None) if result else None
        raw_success = bool(result and result.success)
        raw_error = result.error_message if result else 'Unknown error'
        md_raw = getattr(result, 'markdown', None) if result else None
        if md_raw is None:
            markdown_text = ''
        elif isinstance(md_raw, str):
            markdown_text = md_raw
        else:
            markdown_text = getattr(md_raw, 'raw_markdown', None) or str(md_raw)
        redirected_url = getattr(result, 'redirected_url', None) if result else None
        html_raw = getattr(result, 'html', None) if result else None
        html_length = len(html_raw) if isinstance(html_raw, str) else None
        ok, error_code, error_message = apply_http_status_gate(
            success=raw_success,
            status_code=status_code,
            error_message=None if raw_success else raw_error,
            redirected_url=redirected_url,
            content=markdown_text,
        )
        if ok:
            return CrawlResultVo(
                success=True,
                url=result.url,
                markdown=markdown_text,
                title=getattr(result, 'title', ''),
                status_code=status_code,
                redirected_url=redirected_url,
                html_length=html_length,
                media=getattr(result, 'media', None),
                links=getattr(result, 'links', None),
            )
        return CrawlResultVo(
            success=False,
            url=result.url if result else target_url,
            status_code=status_code,
            redirected_url=redirected_url,
            html_length=html_length,
            error_code=error_code,
            error_message=error_message,
        )
