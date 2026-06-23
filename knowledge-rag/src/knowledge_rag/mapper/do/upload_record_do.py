from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeUploadDocumentRecord(Base):
    """
    文档上传记录表
    """

    __tablename__ = 'knowledge_upload_document_record'
    __table_args__ = {'comment': '文档上传记录表'}

    record_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='上传记录ID')
    doc_title = Column(String(255), nullable=False, comment='文档标题')
    doc_desc = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='文档描述',
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
        comment='文档格式',
    )
    doc_version = Column(String(20), nullable=True, server_default='1.0', comment='文档版本号（上传时预占）')
    is_latest = Column(CHAR(1), nullable=True, server_default='1', comment='是否最新版本（0-否 1-是）')
    version_remark = Column(
        String(255),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='版本说明',
    )
    parse_required = Column(CHAR(1), nullable=True, server_default='1', comment='是否需要MinerU解析（0-否 1-是）')
    original_doc_key = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='原始文件MinIO对象键',
    )
    total_pages = Column(Integer, nullable=True, server_default='0', comment='总页数')
    status = Column(
        String(20),
        nullable=True,
        server_default='PENDING',
        comment='状态 PENDING/LINK_FAILED/WAITING_UPLOAD/UPLOADING/PARSING/COMPLETED/USER_DECISION/CONVERTED/CONVERT_FAILED',
    )
    error_code = Column(
        String(50),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='错误码',
    )
    error_message = Column(Text, nullable=True, comment='错误信息')
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
