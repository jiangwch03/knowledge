from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, LargeBinary, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeDocumentSegmentArchive(Base):
    """文档分段归档表（主表物理删除前快照，便于恢复）"""

    __tablename__ = 'knowledge_document_segment_archive'
    __table_args__ = {'comment': '文档分段归档表'}

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=False, comment='原 segment.id')
    task_id = Column(BigInteger, nullable=False, comment='所属 embedding 任务')
    doc_id = Column(BigInteger, nullable=False, comment='所属文档')
    file_id = Column(BigInteger, nullable=False, comment='所属 knowledge_document_file.id')
    chunk_id = Column(String(64), nullable=False, comment='业务分片 ID')
    chunk_order = Column(Integer, nullable=False, comment='文件内递增序号，从 0 起')
    text = Column(Text, nullable=True, comment='分段正文')
    metadata_json = Column('metadata', Text, nullable=True, comment='元数据 JSON')
    parent_chunk_id = Column(
        String(64),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='子片指向父；无则空',
    )
    skip_embedding = Column(Integer, nullable=True, server_default='0', comment='1=父片不进向量库；0=需要')
    embedding_id = Column(
        String(64),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='Milvus 主键；未写入为空',
    )
    embedding_vector = Column(
        LargeBinary,
        nullable=True,
        comment='Embedding 向量 float32 打包',
    )
    status = Column(String(32), nullable=True, server_default='STORED', comment='STORED/EMBEDDED/VECTOR_STORED')
    release_tag = Column(String(32), nullable=False, server_default='canary', comment='归档时标签')
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='归档时删除标志快照')
    archive_time = Column(DateTime, nullable=False, default=datetime.now, comment='归档时间')
    archive_by = Column(String(64), nullable=True, server_default="''", comment='归档操作者')
    archive_reason = Column(
        String(64),
        nullable=True,
        server_default="''",
        comment='归档原因：pending_delete_cleanup/task_residue/migrate_soft_deleted',
    )
