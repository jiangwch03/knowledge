from enum import Enum


class DocumentStatus(str, Enum):
    """
    knowledge_document 文档主表状态枚举

    CONVERTED: 已生成 Markdown 格式文档
    CHUNKED: 已完成文档分块
    VECTOR_STORED: 已写入向量库
    """

    CONVERTED = 'CONVERTED'
    CHUNKED = 'CHUNKED'
    VECTOR_STORED = 'VECTOR_STORED'
