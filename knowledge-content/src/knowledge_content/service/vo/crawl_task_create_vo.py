"""爬取任务创建 VO（服务层）"""

from pydantic import BaseModel, Field


class CrawlTaskCreateVo(BaseModel):
    """
    爬取任务创建参数 VO

    封装创建爬取任务所需的全部参数，由调用方（如 output_node）构建后传入。
    """

    # 爬取目标URL
    target_url: str = Field(min_length=1, description='爬取目标URL')
    # 爬取策略配置（crawl4ai 参数 JSON）
    crawl_config: dict = Field(min_length=1, description='爬取策略配置')
    # 关联的聊天会话ID
    session_id: int = Field(gt=0, description='关联的聊天会话ID')
    # 任务所属用户ID
    user_id: int = Field(gt=0, description='任务所属用户ID')
    # 任务所属部门ID（可选）
    dept_id: int | None = Field(default=None, gt=0, description='任务所属部门ID')
    # 创建者标识
    create_by: str = Field(default='', description='创建者标识')
