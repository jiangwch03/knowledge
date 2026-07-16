from datetime import datetime

from knowledge_common.vo.base_vo import BaseVo


class UrlRecordUpsertVo(BaseVo):
    """爬取URL记录写入模型"""

    task_id: int
    url: str
    status: str = 'PENDING'
    doc_key: str | None = None
    title: str | None = None
    status_code: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_count: int = 0
    create_by: str = ''
    create_time: datetime | None = None
    update_by: str = ''
    update_time: datetime | None = None
