"""knowledge-content 的 Feign Client。"""

from knowledge_admin.infra.rpc.content.client.document_section_client import DocumentSectionClient
from knowledge_admin.infra.rpc.content.client.embedding_client import EmbeddingClient
from knowledge_admin.infra.rpc.content.client.segment_client import SegmentClient
from knowledge_admin.infra.rpc.content.client.source_file_client import SourceFileClient

__all__ = [
    'DocumentSectionClient',
    'EmbeddingClient',
    'SegmentClient',
    'SourceFileClient',
]
