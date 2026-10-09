"""跨服务调用，按提供方项目分子包。"""

from knowledge_admin.infra.rpc.content import EmbeddingService, SegmentService
from knowledge_admin.infra.rpc.retrieval import QaEvalService

__all__ = [
    'EmbeddingService',
    'QaEvalService',
    'SegmentService',
]
