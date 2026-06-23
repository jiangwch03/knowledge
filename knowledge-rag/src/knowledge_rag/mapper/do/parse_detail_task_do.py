from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeMineruParseDetailTask(Base):
    """
    MinerU解析批次/分段明细表
    """

    __tablename__ = 'knowledge_mineru_parse_detail_task'
    __table_args__ = {'comment': 'MinerU解析批次/分段明细表'}

    detail_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='明细ID')
    parse_task_id = Column(BigInteger, nullable=False, comment='关联解析任务ID')
    sequence_number = Column(Integer, nullable=False, comment='分段序号，用于合并排序')
    batch_id = Column(
        String(64),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='MinerU批次ID（重试会变）',
    )
    data_id = Column(
        String(64),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='MinerU数据ID（重试会变）',
    )
    page_ranges = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='页码范围',
    )
    state = Column(
        String(20),
        nullable=True,
        server_default='WAITING_UPLOAD',
        comment='分段状态 WAITING_UPLOAD/UPLOAD_FAILED/PARSING/PARSED/PARSE_FAILED/RETRIED',
    )
    upload_url = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='上传链接',
    )
    upload_expire_at = Column(DateTime, nullable=True, comment='链接过期时间')
    full_zip_url = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='结果ZIP链接',
    )
    err_msg = Column(Text, nullable=True, comment='错误信息')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0-未删除 2-已删除）')
