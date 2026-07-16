from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size

from knowledge_common.vo.base_vo import BaseVo
from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_common.agent.schema.agent_message_resp_vo import AgentMessageRespVo
from knowledge_common.agent.schema.agent_session_vo import AgentSessionVo
from knowledge_content.enums.confirm_choice_enum import ConfirmChoice

SessionRespVo = AgentSessionVo
MessageRespVo = AgentMessageRespVo


# ==================== 会话管理 ====================


class CreateSessionVo(BaseVo):
    """
    创建会话请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    session_title: str | None = Field(default=None, description='会话标题')
    model_id: int | None = Field(default=None, description='选择的模型ID')


class RenameSessionVo(BaseVo):
    """
    重命名会话请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    session_title: str = Field(..., description='新会话标题')

    @NotBlank(field_name='session_title', message='会话标题不能为空')
    @Size(field_name='session_title', min_length=1, max_length=255, message='会话标题长度不能超过255个字符')
    def get_session_title(self) -> str:
        return self.session_title


class SessionListQueryVo(BaseVo, BasePageQueryModel):
    """
    会话列表查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    title: str | None = Field(default=None, description='标题模糊搜索')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=20, ge=1, le=500, description='每页记录数')


class MessageListQueryVo(BaseVo, BasePageQueryModel):
    """
    消息列表查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=50, ge=1, le=200, description='每页记录数')


# ==================== 聊天交互 ====================


class ChatMessageVo(BaseVo):
    """
    聊天消息请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    content: str = Field(..., min_length=1, description='消息内容')
    model_id: int | None = Field(default=None, gt=0, description='关联的AI模型ID')

    @NotBlank(field_name='content', message='消息内容不能为空')
    def get_content(self) -> str:
        return self.content


class ResumeVo(BaseVo):
    """
    中断恢复请求模型

    - HITL 确认类：resume_value 为 approve / reject（与父图 allowed_decisions 对齐）
    - 自由文本补充（登录、Cookie、范围等）：resume_value 为任意非空文本
    """

    model_config = ConfigDict(alias_generator=to_camel)

    resume_value: str = Field(
        ...,
        min_length=1,
        max_length=8000,
        description='中断恢复值：确认类为 approve/reject；补充信息类为自由文本',
    )
    resume_url: str = Field(default='', description='备用目标URL，无中断时用于重启图兜底')

    @field_validator('resume_value')
    @classmethod
    def validate_resume_value(cls, v: str) -> str:
        text = v.strip()
        if not text:
            raise ValueError('resume_value 不能为空')
        return text


class ConfirmStrategyVo(BaseVo):
    """
    确认策略配置请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    action: str = Field(default='confirm', description='决策动作 confirm/regenerate/modify')
    crawl_config: dict = Field(..., description='crawl4ai 策略配置JSON')


# ==================== 任务管理 ====================


class CrawlTaskRespVo(BaseModel):
    """
    爬取任务响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    task_id: int = Field(..., description='任务ID')
    doc_version: str | None = Field(default=None, description='文档版本号')
    target_url: str = Field(..., description='目标URL')
    status: str = Field(..., description='任务状态')
    progress: int = Field(..., description='进度百分比')
    current_step: str | None = Field(default=None, description='当前步骤')
    success_count: int = Field(default=0, description='成功页面数')
    failed_count: int = Field(default=0, description='失败页面数')
    total_count: int = Field(default=0, description='总页面数')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误信息')
    retry_count: int = Field(default=0, description='已重试次数')
    max_retry_count: int = Field(default=2, description='规则自动重试上限')
    crawl_config: str | None = Field(default=None, description='crawl4ai爬取策略配置JSON')
    started_time: datetime | None = Field(default=None, description='开始时间')
    completed_time: datetime | None = Field(default=None, description='完成时间')
    create_by: str | None = Field(default=None, description='操作用户')
    create_time: datetime = Field(..., description='创建时间')
    update_time: datetime | None = Field(default=None, description='更新时间')


class CrawlTaskListQueryVo(BaseVo, BasePageQueryModel):
    """
    爬取任务列表查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    status: str | None = Field(default=None, description='状态过滤')
    create_by: str | None = Field(default=None, description='操作用户模糊搜索')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=20, ge=1, le=500, description='每页记录数')


class UrlRecordRespVo(BaseModel):
    """
    URL记录响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    id: int = Field(..., description='主键ID')
    task_id: int = Field(..., description='关联任务ID')
    url: str = Field(..., description='原始页面URL')
    status: str = Field(..., description='记录状态 PENDING/SUCCESS/FAILED')
    doc_key: str | None = Field(default=None, description='页面markdown的MinIO对象键')
    title: str | None = Field(default=None, description='页面标题')
    status_code: int | None = Field(default=None, description='HTTP状态码')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误详情')
    retry_count: int = Field(default=0, description='重试次数')
    create_time: datetime = Field(..., description='创建时间')


class UrlRecordListQueryVo(BaseVo, BasePageQueryModel):
    """
    URL记录列表查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    status: str | None = Field(default=None, description='状态过滤')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=50, ge=1, le=200, description='每页记录数')


# ==================== 文档管理 ====================


class CrawlerDocumentRespVo(BaseModel):
    """
    爬取文档响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)

    doc_id: int = Field(..., description='文档ID')
    task_id: int | None = Field(default=None, description='关联任务ID')
    session_id: int | None = Field(default=None, description='关联会话ID')
    session_title: str | None = Field(default=None, description='会话标题')
    doc_title: str = Field(..., description='文档标题')
    doc_desc: str | None = Field(default=None, description='文档描述')
    doc_name: str | None = Field(default=None, description='文件名（首条文件摘要）')
    doc_type: str | None = Field(default=None, description='文档格式（首条文件摘要）')
    doc_version: str | None = Field(default=None, description='文档版本')
    source_url: str | None = Field(default=None, description='来源URL（首条文件摘要）')
    file_count: int | None = Field(default=None, description='文件子表行数')
    status: str = Field(..., description='文档状态')
    is_latest: str | None = Field(default=None, description='是否最新版本')
    create_by: str | None = Field(default=None, description='操作用户')
    del_flag: str | None = Field(default=None, description='删除标识')
    create_time: datetime = Field(..., description='创建时间')


class CrawlerDocumentListQueryVo(BaseVo, BasePageQueryModel):
    """
    爬取文档列表查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    task_id: int | None = Field(default=None, description='任务ID（为空时查询全部文档）')
    doc_title: str | None = Field(default=None, description='文档标题模糊搜索')
    status: str | None = Field(default=None, description='文档状态过滤')
    create_by: str | None = Field(default=None, description='操作用户模糊搜索')
    del_flag: str | None = Field(default=None, description='删除标识过滤')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=20, ge=1, le=500, description='每页记录数')


class EnumOption(BaseModel):
    """
    枚举选项（用于前端下拉框和标签展示）
    """

    model_config = ConfigDict(alias_generator=to_camel)

    value: str = Field(..., description='枚举值')
    label: str = Field(..., description='中文标签')
    type: str = Field(default='info', description='标签类型（success/danger/warning/info）')
