from datetime import datetime

from pydantic import BaseModel, Field


class MineruParseTaskUpdateVO(BaseModel):
    """
    MinerU 解析任务更新值对象（DAO 层 update 操作的字段契约）
    """

    status: str = Field(..., description='任务状态')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误信息')
    batch_id: str | None = Field(default=None, description='MinerU 批次ID')

    def to_update_dict(self, clear_errors: bool = False) -> dict[str, str | datetime | None]:
        """
        转换为 update SQL 所需的字段字典

        :param clear_errors: 是否将 error_code/error_message 显式置空（用于成功状态下清空历史错误信息）
        :return: 字段名到值的映射
        """
        result: dict[str, str | datetime | None] = {'status': self.status, 'update_time': datetime.now()}
        if clear_errors:
            result['error_code'] = None
            result['error_message'] = None
        else:
            if self.error_code is not None:
                result['error_code'] = self.error_code
            if self.error_message is not None:
                result['error_message'] = self.error_message
        if self.batch_id is not None:
            result['batch_id'] = self.batch_id
        return result
