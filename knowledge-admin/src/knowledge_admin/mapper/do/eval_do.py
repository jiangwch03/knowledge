from datetime import datetime

from knowledge_common.config.database import Base
from knowledge_common.config.env import DataBaseConfig
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.utils.common_util import SqlalchemyUtil
from sqlalchemy import CHAR, BigInteger, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import deferred

from knowledge_admin.enums.eval_dataset_status_enum import EvalDatasetStatus


class KnowledgeEvalDataset(Base):
    __tablename__ = 'knowledge_eval_dataset'
    __table_args__ = (
        Index('idx_doc_id', 'doc_id'),
        Index('idx_status', 'status'),
        Index('idx_create_time', 'create_time'),
        {'comment': '知识库测评集'},
    )

    dataset_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False)
    doc_id = Column(BigInteger, nullable=False)
    description = Column(String(500), nullable=True)
    status = Column(String(32), nullable=False, server_default=EvalDatasetStatus.INIT.value)
    item_count = Column(Integer, nullable=True, server_default='0')
    question_count = Column(Integer, nullable=False, server_default='1')
    material_plan = deferred(
        Column(
            Text().with_variant(MEDIUMTEXT(), 'mysql'),
            nullable=True,
            comment='圈资料结果 JSON，含抽中的材料和下载对象名',
        )
    )
    user_id = Column(BigInteger, nullable=True)
    dept_id = Column(BigInteger, nullable=True)
    create_by = Column(String(64), server_default="''")
    create_time = Column(DateTime, default=datetime.now)
    update_by = Column(String(64), server_default="''")
    update_time = Column(DateTime, default=datetime.now)
    del_flag = Column(CHAR(1), server_default=DeleteFlag.NORMAL.value)
    remark = Column(
        String(500),
        nullable=True,
        server_default=SqlalchemyUtil.get_server_default_null(DataBaseConfig.db_type),
    )


class KnowledgeEvalDatasetItem(Base):
    __tablename__ = 'knowledge_eval_dataset_item'
    __table_args__ = (Index('idx_dataset_id', 'dataset_id'), {'comment': '测评集题目'})

    item_id = Column(BigInteger, primary_key=True, autoincrement=True)
    dataset_id = Column(BigInteger, nullable=False)
    question = Column(Text, nullable=False)
    ground_truth = Column(Text, nullable=True)
    reference_excerpts = Column(Text, nullable=True)
    used_chunk_ids = Column(Text, nullable=True)
    keypoints = Column(Text, nullable=True)
    difficulty = Column(String(64), nullable=True)
    sort_order = Column(Integer, server_default='0')
    enabled = Column(Integer, server_default='1')
    create_by = Column(String(64), server_default="''")
    create_time = Column(DateTime, default=datetime.now)
    update_by = Column(String(64), server_default="''")
    update_time = Column(DateTime, default=datetime.now)
    del_flag = Column(CHAR(1), server_default=DeleteFlag.NORMAL.value)


class KnowledgeEvalTask(Base):
    __tablename__ = 'knowledge_eval_task'
    __table_args__ = (
        Index('idx_embedding_task_id', 'embedding_task_id'),
        Index('idx_dataset_id', 'dataset_id'),
        Index('idx_status', 'status'),
        Index('idx_doc_id', 'doc_id'),
        {'comment': '知识库测评任务'},
    )

    eval_task_id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=True)
    embedding_task_id = Column(BigInteger, nullable=False)
    doc_id = Column(BigInteger, nullable=False)
    dataset_id = Column(BigInteger, nullable=False)
    status = Column(String(32), nullable=False, server_default='OPEN')
    publish_time = Column(DateTime, nullable=True)
    user_id = Column(BigInteger, nullable=True)
    dept_id = Column(BigInteger, nullable=True)
    create_by = Column(String(64), server_default="''")
    create_time = Column(DateTime, default=datetime.now)
    update_by = Column(String(64), server_default="''")
    update_time = Column(DateTime, default=datetime.now)
    del_flag = Column(CHAR(1), server_default=DeleteFlag.NORMAL.value)
    remark = Column(String(500), nullable=True)


class KnowledgeEvalRun(Base):
    __tablename__ = 'knowledge_eval_run'
    __table_args__ = (
        Index('idx_eval_task_id', 'eval_task_id'),
        Index('idx_status', 'status'),
        Index('idx_create_time', 'create_time'),
        {'comment': '测评 run'},
    )

    run_id = Column(BigInteger, primary_key=True, autoincrement=True)
    eval_task_id = Column(BigInteger, nullable=False)
    dataset_id = Column(BigInteger, nullable=False)
    embedding_task_id = Column(BigInteger, nullable=False)
    release_tag = Column(String(32), server_default='canary')
    status = Column(String(32), nullable=False, server_default='PENDING')
    dataset_snapshot = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=True)
    summary_metrics = Column(Text, nullable=True)
    report_text = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=True)
    embedding_model_code = Column(String(128), nullable=True)
    llm_version = Column(String(128), nullable=True)
    judge_model_code = Column(String(128), nullable=True)
    error_message = Column(String(2000), nullable=True)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    create_by = Column(String(64), server_default="''")
    create_time = Column(DateTime, default=datetime.now)
    update_by = Column(String(64), server_default="''")
    update_time = Column(DateTime, default=datetime.now)
    del_flag = Column(CHAR(1), server_default=DeleteFlag.NORMAL.value)


class KnowledgeEvalRunItem(Base):
    __tablename__ = 'knowledge_eval_run_item'
    __table_args__ = (Index('idx_run_id', 'run_id'), {'comment': '测评 run 逐题'})

    run_item_id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(BigInteger, nullable=False)
    dataset_item_id = Column(BigInteger, nullable=True)
    question = Column(Text, nullable=True)
    ground_truth = Column(Text, nullable=True)
    reference_excerpts = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=True)
    contexts = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=True)
    answer = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=True)
    metrics = Column(Text, nullable=True)
    sort_order = Column(Integer, server_default='0')
    create_by = Column(String(64), server_default="''")
    create_time = Column(DateTime, default=datetime.now)
    update_by = Column(String(64), server_default="''")
    update_time = Column(DateTime, default=datetime.now)
    del_flag = Column(CHAR(1), server_default=DeleteFlag.NORMAL.value)
