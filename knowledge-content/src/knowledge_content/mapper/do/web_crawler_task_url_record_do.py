from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class WebCrawlerTaskUrlRecord(Base):
    """
    爬取任务URL记录表
    """

    __tablename__ = 'knowledge_web_crawler_task_url_record'
    __table_args__ = {'comment': '爬取任务URL记录表'}

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='主键ID')
    task_id = Column(BigInteger, nullable=False, comment='关联任务ID')
    url = Column(String(1000), nullable=False, comment='原始页面URL')
    status = Column(String(20), nullable=True, server_default='PENDING', comment='记录状态 PENDING/SUCCESS/FAILED')
    doc_key = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='页面markdown的MinIO对象键',
    )
    title = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='页面标题',
    )
    status_code = Column(Integer, nullable=True, comment='HTTP状态码')
    error_code = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='错误码',
    )
    error_message = Column(Text, nullable=True, comment='错误详情')
    retry_count = Column(Integer, nullable=True, server_default='0', comment='重试次数')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(
        DateTime, nullable=True, default=datetime.now, onupdate=datetime.now, comment='更新时间'
    )
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志，见 DeleteFlag 枚举')
