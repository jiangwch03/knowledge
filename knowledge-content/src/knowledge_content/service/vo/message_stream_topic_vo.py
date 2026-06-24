from pydantic import BaseModel, Field


class DocumentParsePending(BaseModel):
    parse_task_id: int = Field(description='文档解析任务ID')


class DocumentMdPending(BaseModel):
    """document.md.pending 消息载荷"""
    record_id: int = Field(description='上传记录ID')