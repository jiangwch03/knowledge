from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeDocumentFile(Base):
    """
    文档文件子表：与单个文件绑定的 MinIO Key / 文件名 / 页 URL 等
    """

    __tablename__ = 'knowledge_document_file'
    __table_args__ = {'comment': '文档文件子表'}

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='文件行主键')
    doc_id = Column(BigInteger, nullable=False, comment='关联 knowledge_document.doc_id')
    task_id = Column(
        BigInteger,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='冗余任务ID（上传任务或爬取任务）',
    )
    doc_name = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='文件名',
    )
    doc_type = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='文档格式 PDF/DOC/DOCX/XLSX/MD',
    )
    source_url = Column(Text, nullable=True, comment='与 doc_key 对应的原始网页URL')
    original_doc_key = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='原始上传文件MinIO对象键',
    )
    doc_key = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='最终Markdown MinIO对象键',
    )
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0-未删除 2-已删除）')
