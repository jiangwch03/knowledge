from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, String

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class AgentSession(Base):
    """Agent 会话表"""

    __tablename__ = 'knowledge_agent_session'
    __table_args__ = {'comment': 'Agent 会话表'}

    session_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='会话ID')
    agent_type = Column(String(50), nullable=False, comment='Agent类型，如 web_crawler')
    session_title = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='会话标题',
    )
    status = Column(String(20), nullable=True, server_default='ACTIVE', comment='会话状态 ACTIVE/CLOSED')
    model_id = Column(
        BigInteger,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='选择的模型ID',
    )
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
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0-未删除 2-已删除）')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='备注',
    )
