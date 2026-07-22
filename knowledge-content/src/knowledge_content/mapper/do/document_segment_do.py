from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Index, Integer, LargeBinary, String, Text
from sqlalchemy.orm import deferred

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeDocumentSegment(Base):
    """文档分段表（release_tag 与 Milvus 对齐）"""

    __tablename__ = 'knowledge_document_segment'
    __table_args__ = (
        Index('idx_task_id', 'task_id'),
        Index('idx_doc_id', 'doc_id'),
        Index('idx_doc_release', 'doc_id', 'release_tag'),
        Index('idx_chunk_id', 'chunk_id'),
        Index('idx_embedding_id', 'embedding_id'),
        # Embedding 热路径：按 task+status 拉批 / COUNT，覆盖 ORDER BY file_id, chunk_order
        Index(
            'idx_task_embed_queue',
            'task_id',
            'skip_embedding',
            'status',
            'del_flag',
            'file_id',
            'chunk_order',
        ),
        {'comment': '文档分段表'},
    )

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='行主键')
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
    # deferred：列表查询不加载大字段；刷 Milvus 时 undefer
    embedding_vector = deferred(
        Column(
            LargeBinary,
            nullable=True,
            comment='Embedding 向量 float32 打包；刷入 Milvus 后可保留',
        )
    )
    status = Column(
        String(32),
        nullable=True,
        server_default='STORED',
        comment='STORED/EMBEDDED/VECTOR_STORED',
    )
    release_tag = Column(
        String(32),
        nullable=False,
        server_default='canary',
        comment='canary/prod/pending_delete，与 Milvus 对齐',
    )
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0-未删除 2-已删除）')
