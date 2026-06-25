from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil
from knowledge_content.enums.mineru_enum import FormulaSwitch, OcrSwitch, TableSwitch


class KnowledgeMineruParseTask(Base):
    """
    MinerU解析任务表
    """

    __tablename__ = 'knowledge_mineru_parse_task'
    __table_args__ = {'comment': 'MinerU解析任务表'}

    parse_task_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='解析任务ID')
    task_id = Column(
        BigInteger,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='关联上传任务ID',
    )
    parse_mode = Column(String(20), nullable=True, server_default='document', comment='解析模式 html/document')
    enable_formula = Column(CHAR(1), nullable=True, server_default=FormulaSwitch.YES.value, comment='公式识别（0-否 1-是）')
    enable_table = Column(CHAR(1), nullable=True, server_default=TableSwitch.YES.value, comment='表格识别（0-否 1-是）')
    language = Column(String(20), nullable=True, server_default='ch', comment='文档语言')
    is_ocr = Column(CHAR(1), nullable=True, server_default=OcrSwitch.NO.value, comment='OCR（0-否 1-是）')
    status = Column(
        String(20),
        nullable=True,
        server_default='PENDING',
        comment='整体状态 PENDING/LINK_FAILED/WAITING_UPLOAD/UPLOADING/PARSING/COMPLETED/FAILED',
    )
    error_code = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='错误码',
    )
    error_message = Column(Text, nullable=True, comment='错误信息')
    batch_id = Column(
        String(64),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='MinerU批次ID',
    )
    user_id = Column(BigInteger, nullable=False, comment='上传用户ID')
    dept_id = Column(
        BigInteger,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='部门ID',
    )
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0-未删除 2-已删除）')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='备注',
    )
