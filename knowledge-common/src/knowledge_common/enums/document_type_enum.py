from enum import Enum


class DocumentType(str, Enum):
    """
    knowledge_document 文档格式枚举

    PDF: PDF 文档
    DOC: DOC 文档
    DOCX: DOCX 文档
    XLSX: XLSX 文档
    MD: Markdown 文档
    """

    PDF = 'PDF'
    DOC = 'DOC'
    DOCX = 'DOCX'
    XLSX = 'XLSX'
    MD = 'MD'
