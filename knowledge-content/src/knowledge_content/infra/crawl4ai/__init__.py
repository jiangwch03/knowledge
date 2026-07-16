"""crawl4ai 基础设施层封装

支持两种调用模式（通过 .env 中 crawl4ai_mode 切换）：
- sdk: 本地 SDK 模式，进程内直接调用 crawl4ai Python 库
- service: 远程服务模式，通过 HTTP 调用独立部署的 crawl4ai Docker 服务
"""

from knowledge_content.infra.crawl4ai.crawl4ai_client import Crawl4aiClient
from knowledge_content.infra.crawl4ai.vo.crawl4ai_vo import CrawlResultVo

__all__ = [
    'Crawl4aiClient',
    'CrawlResultVo',
]
