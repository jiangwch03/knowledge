"""admin → knowledge-content。"""

from knowledge_admin.infra.rpc.content.service.embedding_service import EmbeddingService
from knowledge_admin.infra.rpc.content.service.segment_service import SegmentService

__all__ = [
    'EmbeddingService',
    'SegmentService',
]
