from pydantic import BaseModel, ConfigDict, Field


class DocumentParsePending(BaseModel):
    parse_task_id: int = Field(description='文档解析任务ID')


class DocumentMdPending(BaseModel):
    """document.md.pending 消息载荷"""

    task_id: int = Field(description='上传任务ID')


class CrawlDocumentPending(BaseModel):
    """crawl.document.pending 消息载荷"""

    task_id: int = Field(description='爬取任务ID')
    target_url: str = Field(description='目标URL')


class CrawlTaskPending(BaseModel):
    """crawl.task.pending 消息载荷"""

    task_id: int = Field(description='爬取任务ID')


class EmbeddingPending(BaseModel):
    """embedding.pending 消息载荷"""

    task_id: int = Field(description='Embedding 任务ID', alias='taskId')

    model_config = ConfigDict(populate_by_name=True)
