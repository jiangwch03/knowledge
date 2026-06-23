from enum import Enum


class DocumentSourceType(str, Enum):
    """
    knowledge_document 文档来源类型枚举

    UPLOAD: 手动上传 (0)
    CRAWL: 网页爬取 (1)
    """

    UPLOAD = '0'
    CRAWL = '1'
