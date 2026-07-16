from enum import Enum


class CrawlUrlRecordStatus(str, Enum):
    """爬取任务URL记录状态枚举

    用于 URL 记录表（knowledge_web_crawler_task_url_record），
    记录每个 URL 的爬取结果状态。
    """

    PENDING = 'PENDING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
