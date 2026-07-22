from datetime import datetime

from sqlalchemy import BigInteger, Column, DateTime, Integer, String

from knowledge_common.config.database import Base


class AiModelFunctionAdapter(Base):
    """
    模型功能适配表
    """

    __tablename__ = 'knowledge_ai_model_function_adapter'
    __table_args__ = {'comment': '模型功能适配表'}

    adapter_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='适配ID')
    function_point = Column(String(100), nullable=False, comment='业务功能点')
    param_id = Column(String(64), nullable=False, comment='参数ID，唯一标识业务功能')
    model_id = Column(String(500), nullable=False, comment='关联模型ID，多个用|分隔')
    dimensions = Column(Integer, nullable=True, comment='向量维度（Embedding 业务适配必填）')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now(), comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now(), comment='更新时间')
    del_flag = Column(String(1), nullable=True, server_default='0', comment='删除标志（0代表存在 2代表删除）')
