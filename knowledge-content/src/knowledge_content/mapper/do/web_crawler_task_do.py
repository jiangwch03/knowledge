from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class WebCrawlerTask(Base):
    """
    爬取任务表
    """

    __tablename__ = 'knowledge_web_crawler_task'
    __table_args__ = {'comment': '爬取任务表'}

    task_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务ID')
    doc_version = Column(
        String(20),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='文档版本号（创建时预分配，落库时沿用）',
    )
    target_url = Column(String(1000), nullable=False, comment='目标URL')
    crawl_config = Column(Text, nullable=True, comment='crawl4ai 爬取策略配置JSON')
    status = Column(
        String(20),
        nullable=True,
        server_default='PENDING',
        comment='任务状态，见 CrawlTaskStatus 枚举',
    )
    progress = Column(Integer, nullable=True, server_default='0', comment='进度百分比 0-100')
    current_step = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='当前执行步骤描述',
    )
    success_count = Column(Integer, nullable=True, server_default='0', comment='成功页面数')
    failed_count = Column(Integer, nullable=True, server_default='0', comment='失败页面数')
    total_count = Column(Integer, nullable=True, server_default='0', comment='总页面数')
    error_code = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='错误码',
    )
    error_message = Column(Text, nullable=True, comment='错误信息')
    retry_count = Column(Integer, nullable=True, server_default='0', comment='已重试次数（达到 max_retry_count 后升级为用户人工决策）')
    max_retry_count = Column(
        Integer,
        nullable=True,
        server_default='2',
        comment='规则自动重试上限；LLM 人工重试时 += crawl4ai_rule_retry_limit',
    )
    started_time = Column(DateTime, nullable=True, comment='任务开始时间')
    completed_time = Column(DateTime, nullable=True, comment='任务完成时间')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    dept_id = Column(
        BigInteger,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='部门ID',
    )
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(
        DateTime, nullable=True, default=datetime.now, onupdate=datetime.now, comment='更新时间'
    )
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志，见 DeleteFlag 枚举')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='备注',
    )
