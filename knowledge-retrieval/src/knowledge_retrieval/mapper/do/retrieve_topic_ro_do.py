from sqlalchemy import BigInteger, CHAR, Column, Float, String

from knowledge_common.config.database import Base


class KnowledgeRetrieveTopicRo(Base):
    """主题表只读映射。与 knowledge-content 同表，不引入 content 包。"""

    __tablename__ = 'knowledge_retrieve_topic'
    __table_args__ = {'comment': '知识检索主题（retrieval 只读）', 'extend_existing': True}

    topic_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    topic_name = Column(String(64), nullable=False)
    description = Column(String(1000), nullable=True)
    status = Column(String(32), nullable=False, server_default='READY')
    del_flag = Column(CHAR(1), nullable=True, server_default='0')


class KnowledgeRetrieveTopicKeywordRo(Base):
    """主题关键词只读映射。"""

    __tablename__ = 'knowledge_retrieve_topic_keyword'
    __table_args__ = {'comment': '知识检索主题关键词（retrieval 只读）', 'extend_existing': True}

    keyword_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True)
    topic_id = Column(BigInteger, nullable=False)
    keyword = Column(String(128), nullable=False)
    weight = Column(Float, nullable=False, server_default='0')
    del_flag = Column(CHAR(1), nullable=True, server_default='0')
