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
