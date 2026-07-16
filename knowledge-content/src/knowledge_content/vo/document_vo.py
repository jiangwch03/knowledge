from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size

from knowledge_common.vo.base_vo import BaseVo


class TxtToMarkdownModel(BaseVo):
    """
    TXT 转 Markdown 请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    content: str = Field(..., description='UTF-8 文本内容')

    @NotBlank(field_name='content', message='文本内容不能为空')
    @Size(field_name='content', min_length=1, max_length=524288, message='文本内容大小不能超过 512KB')
    def get_content(self) -> str:
        return self.content


class DocumentFileRespVo(BaseVo):
    """文档文件子表响应"""

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    id: int = Field(..., description='文件行ID')
    doc_id: int = Field(..., description='文档ID')
    task_id: int | None = Field(default=None, description='任务ID')
    doc_name: str | None = Field(default=None, description='文件名')
    doc_type: str | None = Field(default=None, description='文档格式')
    source_url: str | None = Field(default=None, description='原始网页URL')
    original_doc_key: str | None = Field(default=None, description='原始文件MinIO键')
    doc_key: str | None = Field(default=None, description='最终Markdown MinIO键')
