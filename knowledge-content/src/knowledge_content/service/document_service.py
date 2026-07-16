from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.service.llm_chat_service import LlmChatService
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.vo.document_vo import TxtToMarkdownModel


class DocumentService:
    """
    文档主表（knowledge_document）服务层

    仅负责已落库文件表的预览、下载、TXT 转 Markdown 等操作。
    """

    @classmethod
    async def get_next_version(cls, doc_title: str) -> str:
        """
        获取指定文档标题的下一个版本号（主版本递增）

        查询同标题已落库的最大版本号，主版本 +1 返回（如 1.0 → 2.0）。
        查不到或版本号解析异常时返回 '1.0'。

        :param doc_title: 文档标题
        :return: 下一版本号，如 '2.0'
        """
        max_version = await KnowledgeDocumentDao.get_max_version_by_title(doc_title)
        if not max_version:
            return '1.0'
        try:
            major = int(float(max_version))
            return f'{major + 1}.0'
        except (ValueError, IndexError):
            return '1.0'

    @classmethod
    async def _get_document(cls, doc_id: int) -> tuple[KnowledgeDocument, str]:
        """查询文档并下载到本地临时目录

        :param doc_id: 文档ID
        :return: (document 对象, 本地文件路径)
        """
        document = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if not document:
            raise ServiceException('文档不存在')
        if not document.doc_key:
            raise ServiceException('文档对象键为空')
        local_path = await KnowledgeMinioService.download_file(document.doc_key)
        return document, local_path.local_path

    @classmethod
    async def txt_to_markdown(cls, model: TxtToMarkdownModel) -> str:
        """
        TXT 转 Markdown

        委托 LlmChatService.txt_to_markdown 执行大模型转换。

        :param model: TXT 内容
        :return: Markdown 内容
        """
        return await LlmChatService.txt_to_markdown(model.content)

    @classmethod
    async def preview_document(cls, doc_id: int) -> str:
        """预览文档，返回本地路径"""
        _, local_path = await cls._get_document(doc_id)
        return local_path

    @classmethod
    async def download_document(cls, doc_id: int) -> tuple[str, str]:
        """下载文档，返回 (文件名, 本地路径)"""
        document, local_path = await cls._get_document(doc_id)
        filename = document.doc_name or f'{document.doc_title}.md'
        if not filename.lower().endswith('.md'):
            filename = f'{filename}.md'
        return filename, local_path
