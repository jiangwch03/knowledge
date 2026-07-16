import httpx
import re
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.url_util import UrlUtil
from knowledge_content.service.vo.robots_txt_vo import RobotsTxtVo
from knowledge_content.service.vo.page_analysis_vo import PageAnalysisVo
from knowledge_content.service.vo.sitemap_vo import SitemapVo
from knowledge_content.service.vo.anti_crawl_vo import AntiCrawlVo
from urllib.parse import urlparse

class WebCrawlerAnalysisService:
    """
    网页爬取分析服务

    为 Agent 工具提供实际的站点分析能力，包括：
    - robots.txt 获取与解析
    - sitemap.xml 获取与统计
    - 单页面抓取与分析
    - 反爬机制检测
    - URL 模式分析
    """

    @classmethod
    async def fetch_robots_txt(cls, url: str) -> RobotsTxtVo:
        """
        获取并解析目标站点的 robots.txt

        向目标站点 /robots.txt 发起 HTTP GET 请求，逐行解析标准指令（Allow、Disallow、
        Sitemap、Crawl-Delay），返回结构化的 RobotsTxtVo。

        :param url: 目标站点 URL（任意页面 URL 均可，自动提取协议与域名）
        :return: RobotsTxtVo
            - has_robots=True + 解析后的指令列表（正常响应）
            - has_robots=False + error 信息（请求失败或解析异常）
        """
        # 1. 从 URL 提取协议与域名，构造 robots.txt 地址
        parsed = UrlUtil.validate_and_parse_url(url)
        robots_url = f'{parsed.scheme}://{parsed.netloc}/robots.txt'

        # 2. 获取 robots.txt 原始文本内容
        response = await UrlUtil.async_http_get(robots_url, httpx.Response)

        content = response.text
        # 3. 初始化 VO，标记 robots.txt 存在
        vo = RobotsTxtVo(
            has_robots=True,
            allowed_paths=[],
            disallowed_paths=[],
            sitemap_urls=[],
            crawl_delay=None,
        )
        """
        https://milvus.io/robots.txt :
        
        # *
        # 用户代理：* 允许：/

        # Host
        Host: https://milvus.io
        # 主机 主机：https://milvus.io

        # Sitemaps
        Sitemap: https://milvus.io/sitemap.xml

        # 站点地图 站点地图：https://milvus.io/sitemap.xml
        """
        # 4. 逐行解析 robots.txt 标准指令
        for line in content.splitlines():
            line = line.strip()
            if line.lower().startswith('allow:'):
                # 4a. 允许爬取路径
                vo.allowed_paths.append(line.split(':', 1)[1].strip())
            elif line.lower().startswith('disallow:'):
                # 4b. 禁止爬取路径
                vo.disallowed_paths.append(line.split(':', 1)[1].strip())
            elif line.lower().startswith('sitemap:'):
                # 4c. Sitemap 地址
                vo.sitemap_urls.append(line.split(':', 1)[1].strip())
            elif line.lower().startswith('crawl-delay:'):
                # 4d. 爬取延迟（秒），值非法时静默跳过
                try:
                    vo.crawl_delay = int(line.split(':', 1)[1].strip())
                except ValueError:
                    pass

        return vo



    @classmethod
    async def fetch_sitemap(cls, url: str, path_prefix: list[str] | None = None) -> SitemapVo:
        """
        获取并解析 sitemap.xml

        支持两种 XML 格式：
        - 标准 sitemap：直接包含 `<loc>` URL 条目
        - sitemap index：包含多个子 sitemap 的索引（根标签 `<sitemapindex>`），
          自动递归拉取所有子 sitemap 并聚合 URL

        支持路径前缀过滤：当用户 URL 携带路径或多个板块时，可传入 path_prefix 列表，
        只统计匹配这些路径前缀的 URL，使抽样更聚焦。

        :param url: 目标站点URL
        :param path_prefix: 可选，路径前缀列表（如 ["/docs/zh", "/api/zh"]），只统计匹配这些前缀的URL
        :return: SitemapVo
            - has_sitemap=True + URL 统计信息（正常响应）
            - has_sitemap=False（请求失败或解析异常）
        """
        parsed = UrlUtil.validate_and_parse_url(url)
        sitemap_url = f'{parsed.scheme}://{parsed.netloc}/sitemap.xml'


        response = await UrlUtil.async_http_get(sitemap_url, httpx.Response)
        text = response.text

        all_urls: list[str] = []

        # 检测是否为 sitemap index（根标签 <sitemapindex>）
        if re.search(r'<sitemapindex[>\s]', text, re.IGNORECASE):
            sub_sitemap_urls = re.findall(r'<loc>(.*?)</loc>', text)
            logger.info(f'[Analysis] 检测到 sitemap index，包含 {len(sub_sitemap_urls)} 个子 sitemap')
            for sub_url in sub_sitemap_urls:
                try:
                    sub_response = await UrlUtil.async_http_get(sub_url, httpx.Response)
                    sub_urls = re.findall(r'<loc>(.*?)</loc>', sub_response.text)
                    all_urls.extend(sub_urls)
                except Exception as e:
                    logger.opt(exception=True).warning('[Analysis] 拉取子 sitemap 失败: {}, error: {}', sub_url, e)
                    continue
        else:
            # 标准 sitemap 模式
            all_urls = re.findall(r'<loc>(.*?)</loc>', text)

        # 按路径前缀列表过滤（当用户URL中携带多个范围路径时）
        if path_prefix:
            prefixes_clean = [p.strip('/') for p in path_prefix if p.strip('/')]
            if prefixes_clean:
                filtered_urls = [
                    u for u in all_urls
                    if any(prefix in urlparse(u).path for prefix in prefixes_clean)
                ]
                if filtered_urls:
                    logger.info(f'[Analysis] 按路径前缀 {path_prefix} 过滤URL: {len(all_urls)} → {len(filtered_urls)}')
                    all_urls = filtered_urls

        if not all_urls:
            return SitemapVo(has_sitemap=True, total_urls=0)

        total = len(all_urls)

        # 按路径前缀分组（最多分析2000个）
        groups: dict[str, int] = {}
        for u in all_urls[:2000]:
            p = urlparse(u)
            prefix = '/'.join(p.path.strip('/').split('/')[:2]) if p.path.strip('/') else '/'
            groups[prefix] = groups.get(prefix, 0) + 1

        # 抽样（最多10个）
        if len(all_urls) <= 10:
            sample = all_urls[:10]
        else:
            sample = [all_urls[0], all_urls[len(all_urls) // 4], all_urls[len(all_urls) // 2],
                      all_urls[-1]] + all_urls[4:10]

        return SitemapVo(
            has_sitemap=True,
            total_urls=total,
            url_groups=groups,
            sample_urls=sample[:10],
        )


    @classmethod
    async def fetch_page(cls, url: str) -> PageAnalysisVo:
        """
        抓取单页面并分析结构特征

        :param url: 目标页面URL
        :return: PageAnalysisVo
            - title / has_js_rendering / has_pagination / has_popup 等结构化字段（正常响应）
            - error 字段（请求或解析异常时填充）
        """
        parsed = UrlUtil.validate_and_parse_url(url)
        netloc = parsed.netloc

        response = await UrlUtil.async_http_get(url, httpx.Response, headers={'User-Agent': 'Mozilla/5.0'})

        html = response.text

        # 提取标题
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
        title = title_match.group(1).strip() if title_match else ''

        # 分析链接
        internal_links = re.findall(rf'href="(https?://[^"]*{netloc}[^"]*)"', html)
        external_links = re.findall(r'href="(https?://[^"]*)"', html)
        external_links = [l for l in external_links if netloc not in l]

        # 分析特征
        has_js = bool(re.search(r'<script[^>]*src=', html, re.IGNORECASE))
        has_pagination = bool(re.search(r'class="pagination|page-nav|pager"', html, re.IGNORECASE))
        has_popup = bool(re.search(r'class="modal|popup|overlay|cookie-banner"', html, re.IGNORECASE))

        return PageAnalysisVo(
            title=title[:200],
            has_js_rendering=has_js,
            has_pagination=has_pagination,
            pagination_type='page' if has_pagination else 'none',
            has_popup=has_popup,
            popup_type='cookie' if has_popup else 'none',
            content_structure='standard',
            internal_link_count=len(internal_links),
            external_link_count=len(external_links),
        )

    @classmethod
    async def anti_crawling_test(cls, url: str) -> AntiCrawlVo:
        """
        检测反爬机制等级

        :param url: 目标站点URL
        :return: AntiCrawlVo
            - anti_crawl_level / needs_js_rendering / has_captcha 等结构化字段（正常响应）
        """
        UrlUtil.validate_and_parse_url(url)

        response = await UrlUtil.async_http_get(
            url, httpx.Response,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
        )

        status = response.status_code
        headers = dict(response.headers)
        body = response.text[:2000].lower()

        # 检测特征
        has_cloudflare = 'cf-ray' in headers or 'cloudflare' in body
        has_captcha = 'captcha' in body or 'recaptcha' in body
        has_rate_limiting = status == 429
        needs_js = 'javascript' in body and 'noscript' in body

        # 判定反爬等级
        if has_cloudflare or has_captcha:
            level = 'heavy'
        elif has_rate_limiting or needs_js:
            level = 'moderate'
        else:
            level = 'light'

        return AntiCrawlVo(
            anti_crawl_level=level,
            needs_js_rendering=needs_js,
            has_captcha=has_captcha,
            has_rate_limiting=has_rate_limiting,
            has_cloudflare=has_cloudflare,
            detected_headers=list(headers.keys())[:10],
            recommendation=_get_recommendation(level),
        )



    @classmethod
    async def estimate_total_pages(cls, url: str, crawl_config: dict | None = None) -> int:
        """
        粗估目标站点可爬取的总页面数

        从 crawl_config 中提取 max_pages，该值由 Agent 综合站点分析后生成，
        三种来源：用户确认、Agent 评估后用户未改、无法评估/未配置/null 返回 0。
        兼容 Agent 标准路径 crawler_run_config.deep_crawl_strategy.max_pages。
        不再额外请求 sitemap.xml（Agent 生成策略时已分析过）。

        :param url: 目标站点 URL（保留参数签名兼容，当前未使用）
        :param crawl_config: 爬取策略配置 dict
        :return: 估算总页数，无法估算返回 0
        """
        max_pages = cls._extract_max_pages(crawl_config)

        if max_pages <= 0:
            return 0

        # 考虑 filter_chain 排除模式的粗略折减
        filter_factor = cls._estimate_filter_factor(crawl_config)
        return max(int(max_pages * filter_factor), 1)

    @classmethod
    def _resolve_deep_crawl_strategy(cls, crawl_config: dict | None) -> dict:
        """
        解析 deep_crawl_strategy 所在位置

        兼容三种落库/入参形态：
        - Agent 标准：crawler_run_config.deep_crawl_strategy
        - 扁平 crawler：deep_crawl_strategy（在顶层）
        - crawl4ai 序列化：deep_crawl_strategy.params / crawler_run_config 同构
        """
        if not crawl_config or not isinstance(crawl_config, dict):
            return {}

        dcs = crawl_config.get('deep_crawl_strategy')
        if isinstance(dcs, dict):
            return dcs

        crawler_run = crawl_config.get('crawler_run_config')
        if isinstance(crawler_run, dict):
            nested = crawler_run.get('deep_crawl_strategy')
            if isinstance(nested, dict):
                return nested

        return {}

    @classmethod
    def _coerce_max_pages(cls, value) -> int:
        """将 max_pages 转为正整数；null / 非法 / 非正数视为无法粗估（0）"""
        if value is None:
            return 0
        try:
            n = int(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        return n if n > 0 else 0

    @classmethod
    def _extract_max_pages(cls, crawl_config: dict | None) -> int:
        """
        从 crawl_config 中提取 max_pages

        支持路径：
        - 顶层 max_pages
        - deep_crawl_strategy.max_pages（扁平）
        - crawler_run_config.deep_crawl_strategy.max_pages（Agent 标准）
        - deep_crawl_strategy.params.max_pages（序列化）

        :param crawl_config: 爬取策略配置
        :return: max_pages 值，未设置 / null 返回 0
        """
        if not crawl_config:
            return 0

        # 顶层直接有 max_pages
        if 'max_pages' in crawl_config:
            return cls._coerce_max_pages(crawl_config.get('max_pages'))

        dcs = cls._resolve_deep_crawl_strategy(crawl_config)
        if not dcs:
            return 0

        # 原始格式：deep_crawl_strategy.max_pages
        if 'max_pages' in dcs:
            return cls._coerce_max_pages(dcs.get('max_pages'))

        # 序列化格式：deep_crawl_strategy.params.max_pages
        params = dcs.get('params', {})
        if isinstance(params, dict) and 'max_pages' in params:
            return cls._coerce_max_pages(params.get('max_pages'))

        return 0

    @classmethod
    def _estimate_filter_factor(cls, crawl_config: dict | None) -> float:
        """
        根据 filter_chain 估算折减系数

        - 只有 include_patterns（缩小范围）: 不做折减（max_pages 已限制）
        - 有 exclude_patterns（排除部分）: 粗略折减 20%
        - 无 filter_chain: 不做折减

        :param crawl_config: 爬取策略配置
        :return: 折减系数 (0.0 ~ 1.0)
        """
        if not crawl_config:
            return 1.0

        dcs = cls._resolve_deep_crawl_strategy(crawl_config)
        if not dcs:
            return 1.0

        # 原始 / 序列化两种 filter_chain 位置
        filter_chain = dcs.get('filter_chain')
        if not isinstance(filter_chain, dict):
            params = dcs.get('params', {})
            filter_chain = params.get('filter_chain') if isinstance(params, dict) else None
        if not isinstance(filter_chain, dict):
            return 1.0

        # 序列化 FilterChain 可能是 {type, params: {filters: [...]}}，此处仅识别 LLM 原始
        # exclude_patterns 列表形态；识别不到时不做折减
        exclude_patterns = filter_chain.get('exclude_patterns', [])
        if not exclude_patterns:
            params = filter_chain.get('params')
            if isinstance(params, dict):
                exclude_patterns = params.get('exclude_patterns', [])

        if exclude_patterns and len(exclude_patterns) > 0:
            return 0.8

        return 1.0


def _get_recommendation(level: str) -> str:
    """根据反爬等级给出建议"""
    recommendations = {
        'light': '站点反爬较轻，可直接爬取',
        'moderate': '建议启用JS渲染并设置合理延迟',
        'heavy': '反爬机制较强，建议使用代理池和浏览器指纹模拟',
    }
    return recommendations.get(level, '未知反爬等级')
