from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeDocumentEmbeddingTask(Base):
    """文档 Embedding 任务表"""

    __tablename__ = 'knowledge_document_embedding_task'
    __table_args__ = {'comment': '文档 Embedding 任务表'}

    task_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务主键')
    doc_id = Column(BigInteger, nullable=False, comment='关联文档')
    source_type = Column(CHAR(1), nullable=True, server_default='0', comment='来源类型（0-手动上传 1-网页爬取）')
    split_type = Column(String(32), nullable=False, comment='切分策略 TITLE/LENGTH/SEPARATOR/REGEX/SMART')
    split_params = Column(Text, nullable=True, comment='切分参数 JSON 快照')
    status = Column(
        String(32),
        nullable=True,
        server_default='PENDING',
        comment='PENDING/CHUNKING/EMBEDDING/COMPLETED/CHUNK_FAILED/EMBED_FAILED',
    )
    error_message = Column(
        String(2000),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='失败原因',
    )
    chunk_count = Column(
        Integer,
        nullable=True,
        server_default='0',
        comment='需入向量库的 segment 数（不含 skip_embedding 父片）',
    )
    embedded_count = Column(
        Integer,
        nullable=True,
        server_default='0',
        comment='向量化进度：过程中为已离开 STORED 数，完成后为成功写入 Milvus 数',
    )
    embedding_model_code = Column(
        String(128),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='Embedding 模型编码快照',
    )
    dimensions = Column(Integer, nullable=True, comment='向量维度快照')
    user_id = Column(BigInteger, nullable=False, comment='提交用户ID')
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
