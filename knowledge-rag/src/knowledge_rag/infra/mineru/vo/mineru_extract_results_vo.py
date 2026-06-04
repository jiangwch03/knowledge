from typing import Literal

from pydantic import BaseModel, Field, model_validator

class MinerUExtractProgressVo(BaseModel):
    """解析进度"""

    extracted_pages: int | None = Field(None, description='已解析页数')
    total_pages: int | None = Field(None, description='总页数')
    start_time: str | None = Field(None, description='解析开始时间')


class MinerUExtractResultVo(BaseModel):
    """单个文件提取结果"""

    file_name: str = Field(..., description='文件名')
    state: Literal[
        'done',
        'waiting-file',
        'pending',
        'running',
        'failed',
        'converting',
    ] = Field(..., description='任务状态')
    full_zip_url: str | None = Field(None, description='结果压缩包 URL')
    err_msg: str | None = Field(None, description='错误信息')
    data_id: str | None = Field(None, description='业务数据 ID')
    extract_progress: MinerUExtractProgressVo | None = Field(None, description='解析进度')

    @model_validator(mode='after')
    def check_full_zip_url_when_done(self) -> 'MinerUExtractResultVo':
        if self.state == 'done' and not self.full_zip_url:
            raise ValueError('state 为 done 时，full_zip_url 不能为空')
        return self


class MinerUBatchResultRespVo(BaseModel):
    """批量结果数据"""

    batch_id: str = Field(..., description='批量任务 ID')
    extract_result: list[MinerUExtractResultVo] = Field(default=list, description='提取结果列表')