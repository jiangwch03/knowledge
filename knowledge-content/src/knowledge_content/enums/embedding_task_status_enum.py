from enum import Enum


class EmbeddingTaskStatus(str, Enum):
    """knowledge_document_embedding_task.status"""

    PENDING = 'PENDING'  # 待处理：任务已创建，等待消费 embedding.pending
    CHUNKING = 'CHUNKING'  # 切分中：正在按策略切分文档并落 segment
    EMBEDDING = 'EMBEDDING'  # 向量化中：正在 Embedding 并写入向量库
    COMPLETED = 'COMPLETED'  # 已完成（终态）
    CHUNK_FAILED = 'CHUNK_FAILED'  # 切分失败（可重置为 CHUNKING 重试）
    EMBED_FAILED = 'EMBED_FAILED'  # 向量化失败（可重置为 EMBEDDING 重试；切分结果保留）

    @classmethod
    def in_progress_values(cls) -> tuple[str, ...]:
        """进行中状态：同文档不可再提交新任务"""
        return (cls.PENDING.value, cls.CHUNKING.value, cls.EMBEDDING.value)

    @classmethod
    def failed_values(cls) -> tuple[str, ...]:
        """失败终态（可重试）"""
        return (cls.CHUNK_FAILED.value, cls.EMBED_FAILED.value)

    @classmethod
    def terminal_values(cls) -> tuple[str, ...]:
        """终态：消费端直接跳过"""
        return (cls.COMPLETED.value, *cls.failed_values())
