from enum import Enum


class MineruParseTaskStatus(str, Enum):
    """
    knowledge_mineru_parse_task 解析任务状态枚举

    与 knowledge_upload_document_record 上传记录共用主状态值，
    解析任务终态为 FAILED（存在失败情况），不使用 USER_DECISION。
    """

    PENDING = 'PENDING'  # 初始状态：解析任务创建后等待调度处理
    LINK_FAILED = 'LINK_FAILED'  # 申请MinerU批量上传链接失败，等待定时任务重试
    WAITING_UPLOAD = 'WAITING_UPLOAD'  # 已获取上传链接，待将分段文件上传至MinerU
    UPLOADING = 'UPLOADING'  # 所有分段上传至MinerU均失败，等待定时任务重试
    PARSING = 'PARSING'  # 正在MinerU侧解析中（含部分上传成功的场景）
    COMPLETED = 'COMPLETED'  # 所有分段解析完成（终态）
    FAILED = 'FAILED'  # 分段全部解析失败/上传超时（终态），等待用户决策
