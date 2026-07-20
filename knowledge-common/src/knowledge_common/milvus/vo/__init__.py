"""Milvus 行 VO。"""

from knowledge_common.milvus.vo.base import BaseMilvusVo, MilvusSearchHit
from knowledge_common.milvus.vo.document_vector_vo import DocumentVectorVo

__all__ = ['BaseMilvusVo', 'DocumentVectorVo', 'MilvusSearchHit']
