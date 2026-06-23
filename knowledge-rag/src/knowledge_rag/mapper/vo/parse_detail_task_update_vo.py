from datetime import datetime

from pydantic import BaseModel, Field


class MineruParseDetailTaskUpdateVO(BaseModel):
    """
    MinerU 解析分段任务更新值对象（DAO 层 update 操作的字段契约）
    """

    state: str | None = Field(default=None, description='分段状态')
    upload_url: str | None = Field(default=None, description='上传链接')
    upload_expire_at: datetime | None = Field(default=None, description='链接过期时间')
    batch_id: str | None = Field(default=None, description='MinerU 批次ID')
    data_id: str | None = Field(default=None, description='MinerU 数据ID')
    full_zip_url: str | None = Field(default=None, description='结果 ZIP 链接')
    err_msg: str | None = Field(default=None, description='错误信息')

    def to_update_dict(self) -> dict[str, str | datetime]:
        """
        转换为 update SQL 所需的字段字典（排除 None 值）

        :return: 字段名到值的映射
        """
        result: dict[str, str | datetime] = {'update_time': datetime.now()}
        if self.state is not None:
            result['state'] = self.state
        if self.upload_url is not None:
            result['upload_url'] = self.upload_url
        if self.upload_expire_at is not None:
            result['upload_expire_at'] = self.upload_expire_at
        if self.batch_id is not None:
            result['batch_id'] = self.batch_id
        if self.data_id is not None:
            result['data_id'] = self.data_id
        if self.full_zip_url is not None:
            result['full_zip_url'] = self.full_zip_url
        if self.err_msg is not None:
            result['err_msg'] = self.err_msg
        return result
