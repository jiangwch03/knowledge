from enum import Enum


class DocumentUploadStatus(str, Enum):
    """
    knowledge_upload_document_record 上传记录状态枚举

    与 knowledge_mineru_parse_task 解析任务共用主状态值，
    上传记录终态为 USER_DECISION（待人工决策），不使用 FAILED。
    """

    PENDING = 'PENDING'  # 初始状态：上传记录创建后等待调度处理（含重试决策后重新入队）
    LINK_FAILED = 'LINK_FAILED'  # 申请MinerU批量上传链接失败，等待定时任务重试
    WAITING_UPLOAD = 'WAITING_UPLOAD'  # 已获取上传链接，待前端将分段文件上传至MinerU
    UPLOADING = 'UPLOADING'  # 所有分段上传至MinerU均失败，等待定时任务重试
    PARSING = 'PARSING'  # 正在MinerU侧解析中（含部分上传成功、正在解析的场景）
    COMPLETED = 'COMPLETED'  # 所有分段解析完成，进入MD合并阶段（中间状态）
    USER_DECISION = 'USER_DECISION'  # 解析失败/上传超时，待用户决策重试或删除（终态）
    CONVERTED = 'CONVERTED'  # MinerU解析结果已合并为MD并落库知识库文档（终态）
    CONVERT_FAILED = 'CONVERT_FAILED'  # MD合并失败，等待定时任务重试
