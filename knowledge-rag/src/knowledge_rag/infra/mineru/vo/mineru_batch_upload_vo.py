import re

from knowledge_common.exceptions.exception import ServiceException
from pydantic import BaseModel, Field, field_validator, model_validator

from knowledge_rag.enums.mineru_enum import MinerUParseModeEnum

_PAGE_RANGE_SEGMENT_PATTERN = re.compile(r'^[1-9]\d*(-[1-9]\d*|--[1-9]\d*)?$')

_ALLOWED_NAME_SUFFIXES = {
    'pdf',
    'doc',
    'docx',
    'ppt',
    'pptx',
    'xls',
    'xlsx',
    'html',
    'png',
    'jpg',
    'jpeg',
    'jp2',
    'webp',
    'gif',
    'bmp',
}


class MinerUFileItem(BaseModel):
    """MineU 批量上传文件项"""

    name: str = Field(..., description='文件名，需带正确后缀')
    data_id: str | None = Field(None, description='业务数据 ID')
    is_ocr: bool | None = Field(default=False, description='是否启用 OCR')
    page_ranges: str | None = Field(None, description='页码范围')

    @field_validator('name')
    @classmethod
    def check_name_suffix(cls, value: str) -> str:
        if '.' not in value:
            raise ServiceException(f'文件名必须包含后缀，当前文件名: {value}')
        suffix = value.rsplit('.', 1)[-1].lower()
        if suffix not in _ALLOWED_NAME_SUFFIXES:
            raise ServiceException(
                f'文件名后缀仅支持 .pdf、.doc、.docx、.ppt、.pptx、.xls、.xlsx、'
                f'.html、png、jpg、jpeg、jp2、webp、gif、bmp，当前后缀: .{suffix}'
            )
        return value

    @field_validator('page_ranges')
    @classmethod
    def check_page_ranges(cls, value: str | None) -> str | None:
        if value is None:
            return value
        for seg in value.split(','):
            seg = seg.strip()
            if not seg:
                raise ServiceException(
                    f'页码范围格式非法，存在空段，当前值: {value}'
                )
            if not _PAGE_RANGE_SEGMENT_PATTERN.match(seg):
                raise ServiceException(
                    f'页码范围格式非法，当前值: {value}。'
                    f'正确格式为逗号分隔的页码段，支持：'
                    f'单页如 "2"、连续页如 "4-6"、到倒数页如 "2--2"'
                )
        return value


class MinerUBatchUploadReqVo(BaseModel):
    """本地文件批量上传解析请求 Bean"""

    files: list[str] = Field(..., min_length=1, max_length=50, description='本地文件路径列表')
    parse_mode: MinerUParseModeEnum = Field(default=MinerUParseModeEnum.NORMAL, description='解析模式')
    enable_formula: bool = Field(default=True, description='是否开启公式识别')
    enable_table: bool = Field(default=True, description='是否开启表格识别')
    language: str = Field(default='ch', description='文档语言')
    extra_formats: list[str] | None = Field(
        None,
        description='额外导出格式。markdown、json 为默认导出格式，无须设置；该参数仅支持 docx、html、latex 三种格式中的一个或多个。对源文件为 html 的文件无效。',
    )

    @model_validator(mode='after')
    def check_extra_formats(self) -> 'MinerUBatchUploadReqVo':
        if self.extra_formats is not None:
            allowed_formats = {'docx', 'html', 'latex'}
            for fmt in self.extra_formats:
                if fmt not in allowed_formats:
                    raise ServiceException(
                        f'额外导出格式仅支持 docx、html、latex，不支持 {fmt}'
                    )
            for file_path in self.files:
                if file_path.lower().endswith('.html'):
                    raise ServiceException(
                        'extra_formats 对源文件为 html 的文件无效'
                    )
        return self


class MinerUBatchUploadRespVo(BaseModel):
    """本地文件批量上传解析响应"""

    batch_id: str = Field(..., description='批量任务 ID')
    file_urls: list[str] = Field(default=list, description='文件上传预签名链接')
    upload_results: list[bool] = Field(default=list, description='各文件上传是否成功')


class MinerUUploadUrlsVo(BaseModel):
    """申请批量上传链接响应 批量上传文件请求参数"""

    batch_id: str = Field(..., description='批量任务 ID')
    file_urls: list[str] = Field(default=list, description='文件上传预签名链接')
    file_paths: list[str] = Field(default=list, description='本地文件路径列表')

    @model_validator(mode='after')
    def check_length_match(self) -> 'MinerUUploadUrlsVo':
        if len(self.file_urls) != len(self.file_paths):
            raise ServiceException('上传链接数量与文件路径数量不匹配')
        return self

class MinerUUploadFilesRespVo(BaseModel):
    """批量上传文件响应"""
    upload_results: list[bool] = Field(default=list, description='各文件上传是否成功')