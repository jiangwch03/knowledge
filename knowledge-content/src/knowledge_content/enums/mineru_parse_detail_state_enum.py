from enum import Enum


class MineruParseDetailState(str, Enum):
    """
    knowledge_mineru_parse_detail_task 解析分段状态枚举
    """

    WAITING_UPLOAD = 'WAITING_UPLOAD'  # 待上传至MinerU
    UPLOAD_FAILED = 'UPLOAD_FAILED'  # 上传至MinerU失败
    PARSING = 'PARSING'  # 正在MinerU侧解析中
    PARSED = 'PARSED'  # MinerU解析完成
    PARSE_FAILED = 'PARSE_FAILED'  # MinerU解析失败
    RETRIED = 'RETRIED'  # PARSE_FAILED后已重新入队重试
