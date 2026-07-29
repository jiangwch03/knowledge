from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class AgentMessage(Base):
    """Agent 消息表"""

    __tablename__ = 'knowledge_agent_message'
    __table_args__ = {'comment': 'Agent 消息表'}

    message_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='消息ID')
    session_id = Column(BigInteger, nullable=False, comment='关联会话ID')
    role = Column(String(20), nullable=False, comment='消息角色 human/ai/system/tool/business')
    content = Column(Text, nullable=True, comment='消息内容')
    tool_call_id = Column(
        String(100),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='工具调用ID（role=tool时使用）',
    )
    tool_name = Column(
        String(100),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='工具名称（role=tool时使用）',
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
