from enum import Enum


class RetrieveTopicStatus(str, Enum):
    """knowledge_retrieve_topic.status"""

    GENERATING = 'GENERATING'  # 抽词进行中
    READY = 'READY'  # 关键词已写入，可参与路由
    FAILED = 'FAILED'  # 抽词失败
