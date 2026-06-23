from datetime import datetime
from typing import Annotated, Literal

from fastapi import Form
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from pydantic_validation_decorator import NotBlank, Size

from knowledge_common.vo.base_vo import BaseVo
from knowledge_common.vo.base_page_query_vo import BasePageQueryModel
from knowledge_rag.enums.mineru_enum import FormulaSwitch, OcrSwitch, TableSwitch
from knowledge_rag.enums.parse_decision_action_enum import ParseDecisionAction


class UploadDocumentModel(BaseVo):
    """
    上传文档请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_title: str = Field(..., description='文档标题')
    doc_desc: str | None = Field(default=None, description='文档描述')
    version_remark: str | None = Field(default=None, description='版本说明')
    parse_mode: Literal['html', 'document'] | None = Field(default='document', description='解析模式')
    enable_formula: Literal['0', '1'] | None = Field(default=FormulaSwitch.YES.value, description='公式识别')
    enable_table: Literal['0', '1'] | None = Field(default=TableSwitch.YES.value, description='表格识别')
    language: str | None = Field(default='ch', description='文档语言')
    is_ocr: Literal['0', '1'] | None = Field(default=OcrSwitch.NO.value, description='OCR')

    @NotBlank(field_name='doc_title', message='文档标题不能为空')
    @Size(field_name='doc_title', min_length=0, max_length=255, message='文档标题长度不能超过255个字符')
    def get_doc_title(self) -> str:
        return self.doc_title


def upload_document_form(
    doc_title: Annotated[str, Form(description='文档标题')],
    doc_desc: Annotated[str | None, Form(description='文档描述')] = None,
    version_remark: Annotated[str | None, Form(description='版本说明')] = None,
    parse_mode: Annotated[Literal['html', 'document'] | None, Form(description='解析模式')] = 'document',
    enable_formula: Annotated[Literal['0', '1'] | None, Form(description='公式识别')] = FormulaSwitch.YES.value,
    enable_table: Annotated[Literal['0', '1'] | None, Form(description='表格识别')] = TableSwitch.YES.value,
    language: Annotated[str | None, Form(description='文档语言')] = 'ch',
    is_ocr: Annotated[Literal['0', '1'] | None, Form(description='OCR')] = OcrSwitch.NO.value,
) -> UploadDocumentModel:
    """FastAPI Depends 工厂：将 multipart/form-data 字段组装为 UploadDocumentModel"""
    return UploadDocumentModel(
        doc_title=doc_title,
        doc_desc=doc_desc,
        version_remark=version_remark,
        parse_mode=parse_mode,
        enable_formula=enable_formula,
        enable_table=enable_table,
        language=language,
        is_ocr=is_ocr,
    )


class UploadDocumentResponseModel(BaseModel):
    """
    上传文档响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    record_id: int = Field(..., description='上传记录ID')
    doc_title: str = Field(..., description='文档标题')
    doc_name: str = Field(..., description='文件名')
    doc_type: str = Field(..., description='文档格式')
    status: str = Field(..., description='状态')
    create_time: datetime = Field(..., description='创建时间')


class ListDocumentRecordsResponseModel(BaseModel):
    """
    文档上传记录列表响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    record_id: int = Field(..., description='上传记录ID')
    doc_id: int | None = Field(default=None, description='关联文档ID')
    doc_title: str = Field(..., description='文档标题')
    doc_desc: str | None = Field(default=None, description='文档描述')
    doc_name: str = Field(..., description='文件名')
    doc_type: str = Field(..., description='文档格式')
    doc_version: str | None = Field(default=None, description='文档版本号')
    version_remark: str | None = Field(default=None, description='版本说明')
    status: str = Field(..., description='状态')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误信息')
    parse_task_id: int | None = Field(default=None, description='解析任务ID')
    create_time: datetime = Field(..., description='创建时间')
    update_time: datetime | None = Field(default=None, description='更新时间')


class ListDocumentRecordsQueryModel(BaseVo, BasePageQueryModel):
    """
    文档上传记录列表查询模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    doc_title: str | None = Field(default=None, description='文档标题')
    doc_desc: str | None = Field(default=None, description='文档描述')
    doc_type: str | None = Field(default=None, description='文档格式')
    status: str | None = Field(default=None, description='状态')
    page_num: int = Field(default=1, ge=1, description='当前页码')
    page_size: int = Field(default=10, ge=1, le=100, description='每页记录数')


class GetParseTaskResponseModel(BaseModel):
    """
    获取解析任务详情响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    parse_task_id: int = Field(..., description='解析任务ID')
    record_id: int = Field(..., description='关联上传记录ID')
    parse_mode: str = Field(..., description='解析模式')
    status: str = Field(..., description='整体状态')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误信息')
    batch_id: str | None = Field(default=None, description='MinerU批次ID')
    create_time: datetime = Field(..., description='创建时间')
    update_time: datetime = Field(..., description='更新时间')


class ParseTaskItemResponseModel(BaseModel):
    """
    解析任务列表项（用于记录下所有任务概览）
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    parse_task_id: int = Field(..., description='解析任务ID')
    status: str = Field(..., description='任务状态')
    error_code: str | None = Field(default=None, description='错误码')
    create_time: datetime = Field(..., description='创建时间')


class GetParseTaskDetailsResponseModel(BaseModel):
    """
    获取解析任务分段明细响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    detail_id: int = Field(..., description='明细ID')
    parse_task_id: int = Field(..., description='关联解析任务ID')
    sequence_number: int = Field(..., description='分段序号')
    page_ranges: str | None = Field(default=None, description='页码范围')
    state: str = Field(..., description='分段状态')
    err_msg: str | None = Field(default=None, description='错误信息')
    create_time: datetime = Field(..., description='创建时间')


class HandleParseDecisionModel(BaseVo):
    """
    处理解析决策请求模型
    """

    model_config = ConfigDict(alias_generator=to_camel)

    action: ParseDecisionAction = Field(..., description='决策动作')

    @NotBlank(field_name='action', message='决策动作不能为空')
    def get_action(self) -> str:
        return self.action


class GetNextVersionResponseModel(BaseModel):
    """
    获取下一版本号响应模型
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    doc_title: str = Field(..., description='文档标题')
    doc_version: str = Field(..., description='下一版本号')


class DocumentStatusOption(BaseModel):
    """
    文档状态选项（用于前端下拉框）
    """

    model_config = ConfigDict(alias_generator=to_camel)

    value: str = Field(..., description='状态值')
    label: str = Field(..., description='状态标签')
