from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class UploadRecordRow(BaseModel):
    """
    上传记录行（DAO 层返回的原始数据结构，camelCase 字典）
    """

    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True)

    record_id: int = Field(..., description='上传记录ID')
    doc_id: int | None = Field(default=None, description='关联文档ID')
    doc_title: str = Field(..., description='文档标题')
    doc_desc: str | None = Field(default=None, description='文档描述')
    doc_name: str | None = Field(default=None, description='文件名')
    doc_type: str | None = Field(default=None, description='文档格式')
    doc_version: str | None = Field(default=None, description='文档版本号')
    is_latest: str | None = Field(default=None, description='是否最新版本')
    version_remark: str | None = Field(default=None, description='版本说明')
    parse_required: str | None = Field(default=None, description='是否需要MinerU解析')
    original_doc_key: str | None = Field(default=None, description='原始文件MinIO对象键')
    total_pages: int | None = Field(default=None, description='总页数')
    status: str | None = Field(default=None, description='状态')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误信息')
    user_id: int = Field(..., description='上传用户ID')
    dept_id: int | None = Field(default=None, description='部门ID')
    create_by: str | None = Field(default=None, description='创建者')
    create_time: datetime | None = Field(default=None, description='创建时间')
    update_by: str | None = Field(default=None, description='更新者')
    update_time: datetime | None = Field(default=None, description='更新时间')
    del_flag: str | None = Field(default=None, description='删除标志')
    remark: str | None = Field(default=None, description='备注')
