from enum import Enum


class ReleaseTag(str, Enum):
    """document_segment / Milvus release_tag（与 knowledge-content 对齐）"""

    CANARY = 'canary'
    PROD = 'prod'
    PENDING_DELETE = 'pending_delete'
