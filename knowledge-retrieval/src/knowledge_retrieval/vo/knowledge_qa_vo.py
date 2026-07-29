from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size

from knowledge_common.agent.schema.agent_message_resp_vo import AgentMessageRespVo
from knowledge_common.agent.schema.agent_session_vo import AgentSessionVo
from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.vo.base_vo import BaseVo

SessionRespVo = AgentSessionVo
MessageRespVo = AgentMessageRespVo


class CreateSessionVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel)

    session_title: str | None = Field(default=None, description='会话标题')
    model_id: int | None = Field(default=None, description='选择的模型ID')


class RenameSessionVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel)

    session_title: str = Field(..., description='新会话标题')

    @NotBlank(field_name='session_title', message='会话标题不能为空')
    @Size(field_name='session_title', min_length=1, max_length=255, message='会话标题长度不能超过255个字符')
    def get_session_title(self) -> str:
        return self.session_title


class SessionListQueryVo(BaseVo, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel)

    title: str | None = Field(default=None, description='标题模糊搜索')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=20, ge=1, le=500, description='每页记录数')


class MessageListQueryVo(BaseVo, BasePageQueryModel):
    model_config = ConfigDict(alias_generator=to_camel)

    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=50, ge=1, le=200, description='每页记录数')


class ChatMessageVo(BaseVo):
    model_config = ConfigDict(alias_generator=to_camel)

    content: str = Field(..., min_length=1, description='消息内容')
    model_id: int | None = Field(default=None, gt=0, description='关联的AI模型ID')

    @NotBlank(field_name='content', message='消息内容不能为空')
    def get_content(self) -> str:
        return self.content
