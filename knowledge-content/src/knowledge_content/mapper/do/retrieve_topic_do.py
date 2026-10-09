from datetime import datetime

from sqlalchemy import BigInteger, CHAR, Column, DateTime, Float, Integer, String

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.utils.common_util import SqlalchemyUtil


class KnowledgeRetrieveTopic(Base):
    """知识检索主题。"""

    __tablename__ = 'knowledge_retrieve_topic'
    __table_args__ = {'comment': '知识检索主题'}

    topic_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='主键')
    topic_name = Column(String(64), nullable=False, comment='主题名称')
    description = Column(String(1000), nullable=True, comment='主题描述，最多1000字，路由未命中关键词时交给模型')
    task_id = Column(BigInteger, nullable=False, comment='抽词所用的切分任务')
    doc_id = Column(BigInteger, nullable=False, comment='切分任务所属文档')
    keyword_limit = Column(Integer, nullable=False, comment='关键词上限')
    keyword_count = Column(Integer, nullable=False, server_default='0', comment='当前未删除关键词数')
    status = Column(
        String(32),
        nullable=False,
        server_default='GENERATING',
        comment='GENERATING生成中 READY已完成 FAILED失败',
    )
    keep_keywords = Column(CHAR(1), nullable=False, server_default='0', comment='本次抽词是否保留旧关键词（0否 1是）')
    error_message = Column(
        String(2000),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='抽词失败原因',
    )
    user_id = Column(BigInteger, nullable=True, comment='归属用户')
    dept_id = Column(
        BigInteger,
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type, False),
        comment='归属部门',
    )
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0存在 2删除）')
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
        comment='备注',
    )


class KnowledgeTopicEverydayWord(Base):
    """抽词时要丢掉的日常词。全库一份，不挂主题。剔除后 del_flag=2，不再参与过滤。"""

    __tablename__ = 'knowledge_everyday_word'
    __table_args__ = {'comment': '抽词日常词'}

    word_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='主键')
    word = Column(String(64), nullable=False, comment='日常词')
    lang = Column(String(8), nullable=False, server_default='zh', comment='语种 zh中文 en英文')
    word_class = Column(
        String(16),
        nullable=False,
        server_default='other',
        comment='词类 noun名词 verb动词 adj形容词 function虚词 other其他',
    )
    source = Column(
        String(16),
        nullable=False,
        server_default='manual',
        comment='来源 zh_idf中文词频表 en_common常用英语 manual手工录入',
    )
    create_by = Column(String(64), nullable=True, server_default="''", comment='创建者')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_by = Column(String(64), nullable=True, server_default="''", comment='更新者')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0在用 2已剔除）')


class KnowledgeRetrieveTopicKeyword(Base):
    """主题关键词。"""

    __tablename__ = 'knowledge_retrieve_topic_keyword'
    __table_args__ = {'comment': '知识检索主题关键词'}

    keyword_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='主键')
    topic_id = Column(BigInteger, nullable=False, comment='所属主题')
    keyword = Column(String(128), nullable=False, comment='关键词')
    weight = Column(Float, nullable=False, server_default='0', comment='extract_tags 权重')
    create_time = Column(DateTime, nullable=True, default=datetime.now, comment='创建时间')
    update_time = Column(DateTime, nullable=True, default=datetime.now, comment='更新时间')
    del_flag = Column(CHAR(1), nullable=True, server_default='0', comment='删除标志（0存在 2删除）')
