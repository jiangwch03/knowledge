from datetime import datetime

from sqlalchemy import CHAR, BigInteger, Column, DateTime, Integer, String, Text

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeDocumentSegmentRo(Base):
    """分段表只读映射（父片回填）；与 knowledge-content 同表，不引入 content 包依赖。"""

    __tablename__ = 'knowledge_document_segment'
    __table_args__ = {'comment': '文档分段表（retrieval 只读）', 'extend_existing': True}

    id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    chunk_id = Column(String(64), nullable=False)
    text = Column(Text, nullable=True)
    parent_chunk_id = Column(
        String(64),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
    )
    skip_embedding = Column(Integer, nullable=True, server_default='0')
    del_flag = Column(CHAR(1), nullable=True, server_default='0')
    create_time = Column(DateTime, nullable=True, default=datetime.now)
