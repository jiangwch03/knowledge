import json
from datetime import datetime

from pydantic import BaseModel, Field


class CrawlTaskUpdateVo(BaseModel):
    """
    爬取任务更新值对象（DAO 层 update 操作的字段契约）

    统一用于 update_task / update_status / update_progress 等所有 update 场景，
    调用方按需设置字段，DAO 层只接收此 VO 即可完成全部更新。
    """

    status: str | None = Field(default=None, description='任务状态')
    progress: int | None = Field(default=None, description='进度百分比')
    current_step: str | None = Field(default=None, description='当前步骤')
    success_count: int | None = Field(default=None, description='成功页面数')
    failed_count: int | None = Field(default=None, description='失败页面数')
    total_count: int | None = Field(default=None, description='总页面数')
    error_code: str | None = Field(default=None, description='错误码')
    error_message: str | None = Field(default=None, description='错误信息')
    retry_count: int | None = Field(default=None, description='已重试次数')
    max_retry_count: int | None = Field(default=None, description='规则自动重试上限')
    started_time: datetime | None = Field(default=None, description='开始时间')
    completed_time: datetime | None = Field(default=None, description='完成时间')
    update_by: str = Field(default='', description='更新者标识')
    clear_errors: bool = Field(default=False, description='是否将 error_code/error_message 显式置空')
    crawl_config: dict | None = Field(default=None, description='爬取策略配置（JSON 对象）')
    target_url: str | None = Field(default=None, description='目标URL（重试时可改入口）')
    doc_version: str | None = Field(default=None, description='文档版本号（入口变更时重分配）')

    def to_update_dict(self) -> dict:
        """
        转换为 update SQL 所需的字段字典

        :return: 字段名到值的映射
        """
        result: dict = {'update_time': datetime.now()}
        if self.clear_errors:
            result['error_code'] = None
            result['error_message'] = None
        for field_name in [
            'status', 'progress', 'current_step', 'success_count', 'failed_count',
            'total_count', 'error_code', 'error_message', 'retry_count', 'max_retry_count',
            'started_time', 'completed_time', 'update_by', 'target_url', 'doc_version',
        ]:
            value = getattr(self, field_name)
            if value is not None and field_name not in result:
                result[field_name] = value
        if self.crawl_config is not None:
            result['crawl_config'] = json.dumps(self.crawl_config, ensure_ascii=False)
        return result
