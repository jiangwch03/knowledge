from enum import Enum


class CrawlUrlErrorCode(str, Enum):
    """crawl_url 爬取URL级错误码枚举

    用于 URL 记录表（knowledge_web_crawler_task_url_record），
    记录单个 URL 爬取失败的具体原因，供重试策略精准决策。

    与 CrawlTaskErrorCode 的区别：
    - CrawlTaskErrorCode：任务级聚合错误码，用于任务表，面向用户展示
    - CrawlUrlErrorCode：URL 级细分错误码，用于 URL 记录表，面向重试决策
    """

    # 通用爬取失败（未识别具体类型）
    CRAWL_FAILED = 'CRAWL_FAILED'  # 单个URL爬取失败（兜底）

    # 网络与浏览器类（瞬时故障，可规则重试）
    BROWSER_CRASH = 'BROWSER_CRASH'            # 浏览器崩溃
    PAGE_TIMEOUT = 'PAGE_TIMEOUT'              # 页面加载超时
    CONNECTION_RESET = 'CONNECTION_RESET'      # 连接被重置
    RATE_LIMITED = 'RATE_LIMITED'              # 触发速率限制
    CLOUDFLARE_CHALLENGE = 'CLOUDFLARE_CHALLENGE'  # Cloudflare 人机验证拦截

    # 服务端/基础设施类
    SERVICE_HTTP_ERROR = 'SERVICE_HTTP_ERROR'      # crawl4ai服务返回HTTP错误
    SERVICE_CONNECT_ERROR = 'SERVICE_CONNECT_ERROR'  # 无法连接crawl4ai服务
    SERVICE_ERROR = 'SERVICE_ERROR'                # 调用crawl4ai服务异常
    SERVICE_STREAM_ERROR = 'SERVICE_STREAM_ERROR'  # 流式调用异常
    CRAWL4AI_ERROR = 'CRAWL4AI_ERROR'              # SDK模式执行异常
    EMPTY_RESULTS = 'EMPTY_RESULTS'                # 远程服务返回空结果
    EMPTY_CONTENT = 'EMPTY_CONTENT'                # 爬取成功但正文过短/为空（如 css_selector 未命中、挑战页）
    UNRESOLVED_REDIRECT = 'UNRESOLVED_REDIRECT'    # 最终仍为 3xx（重定向未完成 / Cookie 挑战页）

    # 用户输入/配置类（非瞬时故障，不应规则重试）
    INVALID_URL = 'INVALID_URL'            # 无效URL
    FORBIDDEN_PATH = 'FORBIDDEN_PATH'      # 禁止访问的路径
    CONFIG_ERROR = 'CONFIG_ERROR'          # 配置错误
