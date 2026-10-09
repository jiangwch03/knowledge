"""读取上传文档的 Markdown 并切成出题用的节。不写分段表。"""
from __future__ import annotations

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_content.document_section_vo import (
    DocumentSectionListVo,
    DocumentSectionVo,
)
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_file_dao import KnowledgeDocumentFileDao
from knowledge_content.service.document_section_splitter import DocumentSectionSplitter
from knowledge_content.service.minio_service import KnowledgeMinioService


class DocumentSectionService:
    """出题切节。正文从 MinIO 读，结果只返回。"""

    @classmethod
    async def list_sections(cls, doc_id: int) -> DocumentSectionListVo:
        # 步骤1：文档必须存在
        document = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if document is None:
            raise ServiceException('文档不存在')
        # 步骤2：按文件顺序读解析后的 Markdown，逐份切节
        rows = await KnowledgeDocumentFileDao.list_by_doc_id(doc_id)
        sections: list[DocumentSectionVo] = []
        for row in rows:
            doc_key = (row.doc_key or '').strip()
            if not doc_key:
                continue
            text = await KnowledgeMinioService.download_content(doc_key)
            sections.extend(DocumentSectionSplitter.split(text))
        # 步骤3：多份文件拼在一起后，顺序从 0 重新编号
        ordered = [
            section.model_copy(update={'section_order': index})
            for index, section in enumerate(sections)
        ]
        return DocumentSectionListVo(sections=ordered)
