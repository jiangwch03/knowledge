"""
crawl4ai Service 模式实现

通过 HTTP 调用独立部署的 crawl4ai Docker 服务执行爬取，适用于生产环境或资源隔离场景。
Docker 服务默认端口 11235，API 端点 POST /crawl（全量）和 POST /crawl/stream（流式）。
本模块为内部实现，由 Crawl4aiClient 门面统一调度，业务层不应直接引用。
"""

import json
from collections.abc import AsyncIterator

import httpx

from knowledge_common.config.env import Crawl4aiConfig
from knowledge_common.utils.log_util import logger
from knowledge_content.infra.crawl4ai._crawl4ai_config_builder import Crawl4aiConfigBuilder
from knowledge_content.infra.crawl4ai.error_code_mapper import apply_http_status_gate
from knowledge_content.infra.crawl4ai.vo.crawl4ai_vo import CrawlResultVo


class _Crawl4aiServiceClient:
    """crawl4ai 远程服务模式内部实现（HTTP 调用 Docker 部署的 crawl4ai）"""

    # crawl4ai Docker 服务 API 端点
    _CRAWL_ENDPOINT: str = '/crawl'

    @classmethod
    async def crawl(cls, target_url: str, crawl_config: dict | None = None) -> list[CrawlResultVo]:
        """
        通过 HTTP 调用远程 crawl4ai 服务执行爬取

        :param target_url: 目标 URL
        :param crawl_config: 用户策略配置，键名须为 CrawlerRunConfig 支持的属性名
        :return: 爬取结果列表
        """
        # 1. 构建请求体（browser_config + crawler_config 与 Docker API 对齐）
        payload = cls._build_request_payload(target_url, crawl_config)

        # 2. 构建请求头（含认证 Token）
        headers = cls._build_headers()

        # 3. 发送 HTTP 请求
        service_url = Crawl4aiConfig.crawl4ai_service_url.rstrip('/')
        endpoint = f'{service_url}{cls._CRAWL_ENDPOINT}'

        logger.info(f'[Crawl4aiServiceClient] 调用远程服务: url={endpoint}, target={target_url}')

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    endpoint,
                    json=payload,
                    headers=headers,
                    timeout=Crawl4aiConfig.crawl4ai_request_timeout,
                )
                resp.raise_for_status()
                data = resp.json()

        except httpx.HTTPStatusError as e:
            logger.exception(
                '[Crawl4aiServiceClient] 远程服务返回 HTTP {}: {}',
                e.response.status_code,
                e.response.text[:500],
            )
            return [CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_HTTP_ERROR',
                error_message=f'HTTP {e.response.status_code}: {e.response.text[:200]}',
            )]
        except httpx.ConnectError as e:
            logger.exception('[Crawl4aiServiceClient] 无法连接远程服务 {}: {}', service_url, e)
            return [CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_CONNECT_ERROR',
                error_message=f'无法连接 crawl4ai 服务: {service_url}',
            )]
        except Exception as e:
            logger.exception('[Crawl4aiServiceClient] 调用远程服务异常: {}', e)
            return [CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_ERROR',
                error_message=str(e),
            )]

        # 4. 解析响应
        return cls._parse_response(target_url, data)

    @classmethod
    async def crawl_stream(cls, target_url: str, crawl_config: dict | None = None) -> AsyncIterator[CrawlResultVo]:
        """
        通过 HTTP 流式调用远程 crawl4ai 服务（/crawl/stream），每爬完一页立即 yield

        使用 chunked transfer encoding 接收 NDJSON 流，每行一个 CrawlResult JSON 对象。
        流结束时会收到 {"status": "completed"} 信号，自动跳过。

        :param target_url: 目标 URL
        :param crawl_config: 用户策略配置
        :return: 异步生成器，逐个产出 CrawlResultVo
        """
        # 1. 构建请求体，强制 stream=True 触发服务端流式响应
        payload = cls._build_request_payload(target_url, crawl_config)
        payload['crawler_config']['stream'] = True

        headers = cls._build_headers()
        service_url = Crawl4aiConfig.crawl4ai_service_url.rstrip('/')
        endpoint = f'{service_url}/crawl/stream'

        logger.info(f'[Crawl4aiServiceClient] 流式调用远程服务: url={endpoint}, target={target_url}')

        try:
            async with httpx.AsyncClient() as client:
                async with client.stream(
                    'POST', endpoint, json=payload, headers=headers,
                    timeout=Crawl4aiConfig.crawl4ai_request_timeout,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        item = json.loads(line)
                        # 跳过流结束信号（{"status": "completed"}）
                        if item.get('status') == 'completed':
                            continue
                        yield cls._parse_stream_item(target_url, item)

        except httpx.HTTPStatusError as e:
            logger.exception(
                '[Crawl4aiServiceClient] 远程服务返回 HTTP {}: {}',
                e.response.status_code,
                e.response.text[:500],
            )
            yield CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_HTTP_ERROR',
                error_message=f'HTTP {e.response.status_code}: {e.response.text[:200]}',
            )
        except httpx.ConnectError as e:
            logger.exception('[Crawl4aiServiceClient] 无法连接远程服务 {}: {}', service_url, e)
            yield CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_CONNECT_ERROR',
                error_message=f'无法连接 crawl4ai 服务: {service_url}',
            )
        except Exception as e:
            logger.exception('[Crawl4aiServiceClient] 流式调用异常: {}', e)
            yield CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_STREAM_ERROR',
                error_message=str(e),
            )

    @classmethod
    async def probe_page(cls, target_url: str, crawl_config: dict | None = None) -> dict:
        """① 结构化探针（Service 模式）：复用 crawl 接口，映射 links/metadata 等字段"""
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
        if crawl_config:
            _, crawler_run_config, hooks = resolve_strategy_config(crawl_config)
            probe_config = merge_hook_params({**probe_defaults, **crawler_run_config}, hooks)
        else:
            probe_config = probe_defaults
        results = await cls.crawl(target_url, probe_config)
        if not results or not results[0].success:
            err = results[0].error_message if results else '探针无返回'
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
                'error': err,
            }
        item = results[0]
        markdown = item.markdown or ''
        import re
        visible_text = re.sub(r'\s+', ' ', markdown).strip()
        return {
            'success': True,
            'title': item.title or '',
            'html': markdown,
            'visible_text': visible_text,
            'markdown': markdown,
            'links': item.links or {},
            'metadata': {},
            'media': item.media or {},
            'tables': [],
            'status_code': item.status_code,
            'redirected_url': None,
            'error': None,
        }

    @classmethod
    def _parse_stream_item(cls, target_url: str, item: dict) -> CrawlResultVo:
        """解析 /crawl/stream 返回的单行 JSON 为 CrawlResultVo"""
        status_code = item.get('status_code')
        raw_success = bool(item.get('success'))
        raw_error = item.get('error_message', 'Unknown error')
        markdown_text = cls._extract_markdown_text(item.get('markdown'))
        ok, error_code, error_message = apply_http_status_gate(
            success=raw_success,
            status_code=status_code,
            error_message=None if raw_success else raw_error,
            redirected_url=item.get('redirected_url'),
            content=markdown_text,
        )
        html_raw = item.get('html')
        html_length = len(html_raw) if isinstance(html_raw, str) else None
        redirected_url = item.get('redirected_url')
        if ok:
            return CrawlResultVo(
                success=True,
                url=item.get('url', target_url),
                markdown=markdown_text,
                title=item.get('title', ''),
                status_code=status_code,
                redirected_url=redirected_url,
                html_length=html_length,
                media=item.get('media'),
                links=item.get('links'),
            )
        return CrawlResultVo(
            success=False,
            url=item.get('url', target_url),
            status_code=status_code,
            redirected_url=redirected_url,
            html_length=html_length,
            error_code=error_code,
            error_message=error_message,
        )

    @classmethod
    def _build_request_payload(cls, target_url: str, crawl_config: dict | None) -> dict:
        """
        构建 Docker API 请求体

        crawl4ai Docker /crawl 端点接受：
        - urls: 目标 URL 列表
        - browser_config: 浏览器配置字典
        - crawler_config: 爬虫运行配置字典
        """
        payload: dict = {
            'urls': [target_url],
            'browser_config': {
                'headless': Crawl4aiConfig.crawl4ai_headless,
                'user_agent': Crawl4aiConfig.crawl4ai_user_agent,
                'viewport_width': Crawl4aiConfig.crawl4ai_viewport_width,
                'viewport_height': Crawl4aiConfig.crawl4ai_viewport_height,
                'enable_stealth': Crawl4aiConfig.crawl4ai_enable_stealth,
                'verbose': Crawl4aiConfig.crawl4ai_verbose,
            },
            'crawler_config': {
                'cache_mode': 'enabled',                                       # 缓存固定开启
                'excluded_tags': Crawl4aiConfig.crawl4ai_excluded_tags,        # 排除噪音标签
                'only_text': Crawl4aiConfig.crawl4ai_only_text,                # 保留结构化输出
                'word_count_threshold': Crawl4aiConfig.crawl4ai_word_count_threshold,  # 过滤零碎内容块
                'stream': Crawl4aiConfig.crawl4ai_stream,                      # 流式返回结果
            },
        }

        # 合并用户策略配置到 crawler_config（覆盖默认值）
        # 将 LLM JSON 格式转换为 crawl4ai {type, params} 序列化格式，Docker 服务可正确反序列化
        if crawl_config:
            serialized = Crawl4aiConfigBuilder.serialize_crawl_config(crawl_config)
            payload['crawler_config'].update(serialized)

        return payload

    @classmethod
    def _build_headers(cls) -> dict[str, str]:
        """构建 HTTP 请求头，含认证 Token（若配置了 api_token）"""
        headers: dict[str, str] = {'Content-Type': 'application/json'}
        if Crawl4aiConfig.crawl4ai_api_token:
            headers['Authorization'] = f'Bearer {Crawl4aiConfig.crawl4ai_api_token}'
        return headers

    @classmethod
    def _parse_response(cls, target_url: str, data: dict) -> list[CrawlResultVo]:
        """
        解析 Docker API 响应

        响应格式：{ "success": bool, "results": [{ "url": ..., "success": ..., "markdown": ..., ... }] }
        注意：Docker API 的 markdown 字段可能是 dict（含 raw_markdown/markdown_v2 等子字段），需兼容处理。
        """
        if not data.get('success', False):
            return [CrawlResultVo(
                success=False,
                url=target_url,
                error_code='SERVICE_CRAWL_FAILED',
                error_message=data.get('error', '远程服务返回失败'),
            )]

        results: list[CrawlResultVo] = []
        for item in data.get('results', []):
            status_code = item.get('status_code')
            raw_success = bool(item.get('success'))
            raw_error = item.get('error_message', 'Unknown error')
            markdown_text = cls._extract_markdown_text(item.get('markdown'))
            ok, error_code, error_message = apply_http_status_gate(
                success=raw_success,
                status_code=status_code,
                error_message=None if raw_success else raw_error,
                redirected_url=item.get('redirected_url'),
                content=markdown_text,
            )
            html_raw = item.get('html')
            html_length = len(html_raw) if isinstance(html_raw, str) else None
            redirected_url = item.get('redirected_url')
            if ok:
                results.append(CrawlResultVo(
                    success=True,
                    url=item.get('url', target_url),
                    markdown=markdown_text,
                    title=item.get('title', ''),
                    status_code=status_code,
                    redirected_url=redirected_url,
                    html_length=html_length,
                    media=item.get('media'),
                    links=item.get('links'),
                ))
            else:
                results.append(CrawlResultVo(
                    success=False,
                    url=item.get('url', target_url),
                    status_code=status_code,
                    redirected_url=redirected_url,
                    html_length=html_length,
                    error_code=error_code,
                    error_message=error_message,
                ))

        if not results:
            return [CrawlResultVo(
                success=False,
                url=target_url,
                error_code='EMPTY_RESULTS',
                error_message='远程服务返回空结果',
            )]

        return results

    @classmethod
    def _extract_markdown_text(cls, markdown_value) -> str:
        """
        从 Docker API 返回的 markdown 字段中提取纯文本

        Docker API 可能返回两种格式：
        - 字符串：直接作为 Markdown 内容
        - dict：{ "raw_markdown": "...", "markdown_v2": "...", "fit_html": "..." }，取 raw_markdown
        """
        if markdown_value is None:
            return ''
        if isinstance(markdown_value, str):
            return markdown_value
        if isinstance(markdown_value, dict):
            return markdown_value.get('raw_markdown', '') or markdown_value.get('markdown_v2', '')
        return str(markdown_value)
