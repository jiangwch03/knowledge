from enum import Enum


class SegmentStatus(str, Enum):
    """knowledge_document_segment.status"""

    STORED = 'STORED'
    EMBEDDED = 'EMBEDDED'  # 向量已写入 MySQL，待刷 Milvus
    VECTOR_STORED = 'VECTOR_STORED'


class ReleaseTag(str, Enum):
    """document_file_segment / Milvus release_tag（权威在表 ↔ Milvus）"""

    CANARY = 'canary'
    PROD = 'prod'
    PENDING_DELETE = 'pending_delete'


class SegmentArchiveReason(str, Enum):
    """knowledge_document_segment_archive.archive_reason"""

    PENDING_DELETE_CLEANUP = 'pending_delete_cleanup'  # 发布后异步清旧 prod
    TASK_RESIDUE = 'task_residue'  # 删除 canary / 失败任务残留
    MIGRATE_SOFT_DELETED = 'migrate_soft_deleted'  # 历史软删一次性迁入
