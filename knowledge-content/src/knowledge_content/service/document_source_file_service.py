"""按文档列出解析后的 Markdown 对象键，供 admin 自己去 MinIO 下载。"""
from __future__ import annotations

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_content.source_file_vo import (
    SourceMarkdownFileListVo,
    SourceMarkdownFileVo,
)
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_file_dao import KnowledgeDocumentFileDao


class DocumentSourceFileService:
    """原文文件目录。不读对象内容。"""

    @classmethod
    async def list_source_files(cls, doc_id: int) -> SourceMarkdownFileListVo:
        document = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if document is None:
            raise ServiceException('文档不存在')
        rows = await KnowledgeDocumentFileDao.list_by_doc_id(doc_id)
        files = [
            SourceMarkdownFileVo(
                file_id=int(row.id),
                doc_id=int(row.doc_id),
                doc_name=row.doc_name or '',
                source_url=row.source_url,
                doc_key=row.doc_key,
            )
            for row in rows
            if (row.doc_key or '').strip()
        ]
        return SourceMarkdownFileListVo(files=files)
