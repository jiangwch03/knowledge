"""
crawl4ai 策略配置构建器

将 LLM 生成的声明式 JSON 配置（纯 dict）转换为 crawl4ai 所需的格式。
SDK 模式和 Service 模式共用，分别提供：
- build_crawl_config(): 构建 Python 对象（SDK 模式直接传给 CrawlerRunConfig）
- serialize_crawl_config(): 转换为 crawl4ai {type, params} 序列化格式（Service 模式 HTTP JSON）

crawl4ai Docker 服务通过 to_serializable_dict / from_serializable_dict 实现配置的
序列化与反序列化，复杂对象统一采用 {"type": "<ClassName>", "params": {...}} 格式传递。

支持构建的复杂对象：
- markdown_generator → DefaultMarkdownGenerator(content_filter=PruningContentFilter(...))
- deep_crawl_strategy → BFSDeepCrawlStrategy / DFSDeepCrawlStrategy / BestFirstCrawlingStrategy
- cache_mode / match_mode → 枚举值
"""

from crawl4ai import CacheMode, MatchMode
from crawl4ai.content_filter_strategy import (
    BM25ContentFilter,
    PruningContentFilter,
    RelevantContentFilter,
)
from crawl4ai.deep_crawling import (
    BFSDeepCrawlStrategy,
    BestFirstCrawlingStrategy,
    DFSDeepCrawlStrategy,
)
from crawl4ai.deep_crawling.filters import (
    FilterChain,
    URLPatternFilter,
)
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from knowledge_common.utils.log_util import logger

# ─── 类型注册表 ────────────────────────────────────────────────

# content_filter "type" 字段 → 类
_CONTENT_FILTER_TYPES: dict[str, type[RelevantContentFilter]] = {
    'PruningContentFilter': PruningContentFilter,
    'BM25ContentFilter': BM25ContentFilter,
}

# deep_crawl_strategy "crawl_strategy" 字段 → 类
_DEEP_CRAWL_STRATEGY_TYPES: dict[str, type] = {
    'BFSDeepCrawlStrategy': BFSDeepCrawlStrategy,
    'DFSDeepCrawlStrategy': DFSDeepCrawlStrategy,
    'BestFirstCrawlingStrategy': BestFirstCrawlingStrategy,
}

# 枚举类型注册：CrawlerRunConfig 参数名 → (枚举类, 默认值)
_ENUM_FIELDS: dict[str, tuple[type, object]] = {
    'cache_mode': (CacheMode, CacheMode.ENABLED),
    'match_mode': (MatchMode, MatchMode.OR),
}

# Service 模式下当前 Builder 尚不支持序列化构建的复杂对象键
# LLM 若生成了这些键，serialize_crawl_config 会记录警告并剔除
_UNSUPPORTED_COMPLEX_KEYS: set[str] = {
    'extraction_strategy',
    'chunking_strategy',
    'scraping_strategy',
    'table_extraction',
    'proxy_rotation_strategy',
    'geolocation',
}


class Crawl4aiConfigBuilder:
    """
    crawl4ai 策略配置构建器

    职责：将 LLM 生成的声明式 JSON dict 转换为 crawl4ai 所需的格式。
    - SDK 模式：构建为 Python 对象实例（直接传给 CrawlerRunConfig）
    - Service 模式：转换为 crawl4ai {type, params} 序列化格式（通过 HTTP JSON 传递给 Docker 服务）
    """

    @classmethod
    def build_crawl_config(cls, crawl_config: dict) -> dict:
        """
        将声明式 JSON 配置中的复杂对象字段构建为 Python 对象

        转换规则：
        1. 枚举字段（cache_mode/match_mode）：字符串 → 枚举值
        2. markdown_generator：嵌套 dict → DefaultMarkdownGenerator 实例
        3. deep_crawl_strategy：嵌套 dict → BFS/DFS/BestFirst 策略实例

        :param crawl_config: LLM 生成的原始策略配置 dict
        :return: 转换后的配置 dict，复杂对象已替换为 Python 实例
        """
        result = dict(crawl_config)

        # 步骤1：枚举字段字符串 → 枚举值
        cls._convert_enum_fields(result)

        # 步骤2：markdown_generator dict → DefaultMarkdownGenerator 实例
        if 'markdown_generator' in result and isinstance(result['markdown_generator'], dict):
            result['markdown_generator'] = cls._build_markdown_generator(result['markdown_generator'])

        # 步骤3：deep_crawl_strategy dict → DeepCrawlStrategy 实例
        if 'deep_crawl_strategy' in result and isinstance(result['deep_crawl_strategy'], dict):
            result['deep_crawl_strategy'] = cls._build_deep_crawl_strategy(result['deep_crawl_strategy'])

        # 步骤4：剔除 Builder 尚不支持序列化的复杂对象键（避免传裸 dict 给 CrawlerRunConfig）
        for key in _UNSUPPORTED_COMPLEX_KEYS:
            if key in result:
                logger.warning(
                    f'[Crawl4aiConfigBuilder] 当前 Builder 不支持构建 {key}，已剔除'
                )
                del result[key]

        return result

    @classmethod
    def serialize_crawl_config(cls, crawl_config: dict) -> dict:
        """
        将 LLM 生成的声明式 JSON 配置转换为 crawl4ai Docker 服务的 {type, params} 序列化格式

        crawl4ai Docker 服务通过 from_serializable_dict 反序列化请求体中的配置，
        复杂对象需采用 {"type": "<ClassName>", "params": {...}} 格式传递，
        基本类型（str/int/bool/list）可直接传递。

        转换规则：
        1. 枚举字段（cache_mode/match_mode）：字符串 → {"type": "CacheMode", "params": "BYPASS"}
        2. markdown_generator：嵌套 dict → {"type": "DefaultMarkdownGenerator", "params": {...}}
        3. deep_crawl_strategy：嵌套 dict → {"type": "BFSDeepCrawlStrategy", "params": {...}}
        4. 尚不支持的复杂对象键（extraction_strategy 等）：记录警告并剔除

        :param crawl_config: LLM 生成的原始策略配置 dict
        :return: crawl4ai 序列化格式的配置 dict，可直接作为 Docker API 请求体
        """
        result: dict = {}

        for key, value in crawl_config.items():
            # 步骤1：枚举字段字符串 → {type, params} 格式
            # crawl4ai from_serializable_dict 使用 cls(value) 而非 cls[name]，
            # 因此 params 必须是枚举的 value（小写），而非 name（大写）
            if key in _ENUM_FIELDS and isinstance(value, str):
                enum_cls, default = _ENUM_FIELDS[key]
                try:
                    enum_value = enum_cls[value.upper()].value
                except KeyError:
                    logger.warning(
                        f'[Crawl4aiConfigBuilder] 未知枚举值 {key}={value}，使用默认值 {default.value}'
                    )
                    enum_value = default.value
                result[key] = {'type': enum_cls.__name__, 'params': enum_value}
                continue

            # 步骤2：markdown_generator → {type, params} 格式
            if key == 'markdown_generator' and isinstance(value, dict):
                result[key] = cls._serialize_markdown_generator(value)
                continue

            # 步骤3：deep_crawl_strategy → {type, params} 格式
            if key == 'deep_crawl_strategy' and isinstance(value, dict):
                result[key] = cls._serialize_deep_crawl_strategy(value)
                continue

            # 步骤4：尚不支持的复杂对象键，记录警告并剔除
            if key in _UNSUPPORTED_COMPLEX_KEYS:
                logger.warning(
                    f'[Crawl4aiConfigBuilder] 当前 Builder 不支持序列化 {key}，已剔除'
                )
                continue

            # 其余基本类型参数直接透传
            result[key] = value

        return result

    # ─── 私有构建方法 ────────────────────────────────────────────

    @classmethod
    def _convert_enum_fields(cls, config: dict) -> None:
        """将配置中的枚举字段从字符串转换为枚举值（就地修改）"""
        for field_name, (enum_cls, default) in _ENUM_FIELDS.items():
            if field_name not in config:
                continue
            value = config[field_name]
            if isinstance(value, str):
                try:
                    config[field_name] = enum_cls[value.upper()]
                except KeyError:
                    logger.warning(
                        f'[Crawl4aiConfigBuilder] 未知枚举值 {field_name}={value}，使用默认值 {default}'
                    )
                    config[field_name] = default

    @classmethod
    def _build_markdown_generator(cls, config: dict) -> DefaultMarkdownGenerator:
        """
        构建 MarkdownGenerator 实例

        JSON 格式示例：
        {
          "type": "DefaultMarkdownGenerator",
          "content_filter": { "type": "PruningContentFilter", "threshold": 0.48 },
          "options": { "content_source": "cleaned_html" }
        }
        """
        content_filter = None
        if 'content_filter' in config and isinstance(config['content_filter'], dict):
            content_filter = cls._build_content_filter(config['content_filter'])

        return DefaultMarkdownGenerator(
            content_filter=content_filter,
            options=config.get('options'),
            content_source=config.get('content_source', 'cleaned_html'),
        )

    @classmethod
    def _build_content_filter(cls, config: dict) -> RelevantContentFilter | None:
        """
        根据 type 字段构建 ContentFilter 实例

        支持的 type 值：PruningContentFilter, BM25ContentFilter
        """
        filter_type = config.get('type', 'PruningContentFilter')
        filter_cls = _CONTENT_FILTER_TYPES.get(filter_type)
        if filter_cls is None:
            logger.warning(f'[Crawl4aiConfigBuilder] 未知 content_filter type: {filter_type}，跳过构建')
            return None

        # 提取构造参数（排除 type 字段本身）
        params = {k: v for k, v in config.items() if k != 'type'}
        return filter_cls(**params)

    @classmethod
    def _build_filter_chain(cls, config: dict) -> FilterChain:
        """
        根据 include_patterns / exclude_patterns 构建 FilterChain

        URLPatternFilter 签名：patterns + use_glob(True) + reverse(False)
        - include_patterns: 只保留匹配模式的 URL → URLPatternFilter(patterns=...)
        - exclude_patterns: 排除匹配模式的 URL   → URLPatternFilter(patterns=..., reverse=True)

        JSON 格式示例：
        {
          "include_patterns": ["https://example.com/docs/*"],
          "exclude_patterns": ["*/login", "*/admin"]
        }
        """
        filters: list = []
        include_patterns = config.get('include_patterns')
        exclude_patterns = config.get('exclude_patterns')

        if include_patterns:
            filters.append(URLPatternFilter(patterns=include_patterns))
        if exclude_patterns:
            filters.append(URLPatternFilter(patterns=exclude_patterns, reverse=True))

        return FilterChain(filters)

    @classmethod
    def _build_deep_crawl_strategy(cls, config: dict) -> BFSDeepCrawlStrategy | None:
        """
        构建 DeepCrawlStrategy 实例

        JSON 格式示例：
        {
          "crawl_strategy": "BFSDeepCrawlStrategy",
          "max_depth": 3,
          "include_external": false,
          "max_pages": 200,
          "filter_chain": { "include_patterns": [...], "exclude_patterns": [...] },
          "url_scorer": { "keywords": [...], "weight": 0.5 }
        }
        """
        strategy_type = config.get('crawl_strategy', 'BFSDeepCrawlStrategy')
        strategy_cls = _DEEP_CRAWL_STRATEGY_TYPES.get(strategy_type)
        if strategy_cls is None:
            logger.warning(f'[Crawl4aiConfigBuilder] 未知 deep_crawl_strategy type: {strategy_type}，跳过构建')
            return None

        # 构建 FilterChain（如有）
        filter_chain = None
        if 'filter_chain' in config and isinstance(config['filter_chain'], dict):
            filter_chain = cls._build_filter_chain(config['filter_chain'])

        # url_scorer 暂不支持从 JSON 构建（crawl4ai 当前版本无 KeywordRelevanceScorer，
        # url_scorer 接受可调用对象，需要代码层按需定制），留空使用默认行为

        return strategy_cls(
            max_depth=config.get('max_depth', 1),
            filter_chain=filter_chain,
            url_scorer=None,
            include_external=config.get('include_external', False),
            # LLM 输出 null 表示不限制，crawl4ai 用 float('inf') 表达，None 会导致类型错误
            max_pages=config.get('max_pages') or float('inf'),
            score_threshold=config.get('score_threshold') or float('-inf'),
        )

    # ─── Service 模式序列化私有方法 ─────────────────────────────────

    @classmethod
    def _serialize_markdown_generator(cls, config: dict) -> dict:
        """
        将 LLM JSON 格式的 markdown_generator 转换为 crawl4ai {type, params} 序列化格式

        LLM JSON 格式：
        {"type": "DefaultMarkdownGenerator", "content_filter": {...}, "content_source": "..."}

        crawl4ai 序列化格式：
        {"type": "DefaultMarkdownGenerator", "params": {"content_filter": {...}, "content_source": "..."}}
        """
        params: dict = {}

        # content_filter 嵌套序列化
        if 'content_filter' in config and isinstance(config['content_filter'], dict):
            params['content_filter'] = cls._serialize_content_filter(config['content_filter'])

        # options 和 content_source 直接透传（均为基本类型）
        if 'options' in config:
            params['options'] = config['options']
        if 'content_source' in config:
            params['content_source'] = config['content_source']

        return {'type': 'DefaultMarkdownGenerator', 'params': params}

    @classmethod
    def _serialize_content_filter(cls, config: dict) -> dict:
        """
        将 LLM JSON 格式的 content_filter 转换为 crawl4ai {type, params} 序列化格式

        LLM JSON 格式：
        {"type": "PruningContentFilter", "threshold": 0.3, "threshold_type": "fixed"}

        crawl4ai 序列化格式：
        {"type": "PruningContentFilter", "params": {"threshold": 0.3, "threshold_type": "fixed"}}
        """
        filter_type = config.get('type', 'PruningContentFilter')
        params = {k: v for k, v in config.items() if k != 'type'}
        return {'type': filter_type, 'params': params}

    @classmethod
    def _serialize_deep_crawl_strategy(cls, config: dict) -> dict:
        """
        将 LLM JSON 格式的 deep_crawl_strategy 转换为 crawl4ai {type, params} 序列化格式

        LLM JSON 格式（crawl_strategy 字段为类型名，其余为构造参数）：
        {"crawl_strategy": "BFSDeepCrawlStrategy", "max_depth": 1, "filter_chain": {...}}

        crawl4ai 序列化格式（crawl_strategy 提升为 type，filter_chain 递归序列化）：
        {"type": "BFSDeepCrawlStrategy", "params": {"max_depth": 1, "filter_chain": {...}}}
        """
        strategy_type = config.get('crawl_strategy', 'BFSDeepCrawlStrategy')
        params: dict = {}

        for k, v in config.items():
            if k == 'crawl_strategy':
                continue  # crawl_strategy 已提升为 type
            if k == 'filter_chain' and isinstance(v, dict):
                params['filter_chain'] = cls._serialize_filter_chain(v)
            else:
                params[k] = v

        return {'type': strategy_type, 'params': params}

    @classmethod
    def _serialize_filter_chain(cls, config: dict) -> dict:
        """
        将 LLM JSON 格式的 filter_chain 转换为 crawl4ai {type, params} 序列化格式

        LLM JSON 格式：
        {"include_patterns": [...], "exclude_patterns": [...]}

        crawl4ai 序列化格式：
        {"type": "FilterChain", "params": {"filters": [
            {"type": "URLPatternFilter", "params": {"patterns": [...]}},
            {"type": "URLPatternFilter", "params": {"patterns": [...], "reverse": true}}
        ]}}
        """
        filters: list[dict] = []

        if config.get('include_patterns'):
            filters.append({
                'type': 'URLPatternFilter',
                'params': {'patterns': config['include_patterns']},
            })
        if config.get('exclude_patterns'):
            filters.append({
                'type': 'URLPatternFilter',
                'params': {'patterns': config['exclude_patterns'], 'reverse': True},
            })

        return {'type': 'FilterChain', 'params': {'filters': filters}}
