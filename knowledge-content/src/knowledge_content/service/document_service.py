import zipfile
from pathlib import Path

from knowledge_common.config.env import UploadConfig
from knowledge_common.enums.document_source_type_enum import DocumentSourceType
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.service.llm_chat_service import LlmChatService
from knowledge_content.mapper.dao.document_dao import KnowledgeDocumentDao
from knowledge_content.mapper.dao.document_file_dao import KnowledgeDocumentFileDao
from knowledge_content.mapper.do.document_do import KnowledgeDocument
from knowledge_content.mapper.do.document_file_do import KnowledgeDocumentFile
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.vo.document_vo import DocumentFileRespVo, TxtToMarkdownModel


class DocumentService:
    """
    文档主表（knowledge_document）服务层

    预览、下载、文件列表：文件内容从 knowledge_document_file 读取。
    """

    @classmethod
    async def get_next_version(cls, doc_title: str) -> str:
        max_version = await KnowledgeDocumentDao.get_max_version_by_title(doc_title)
        if not max_version:
            return '1.0'
        try:
            major = int(float(max_version))
            return f'{major + 1}.0'
        except (ValueError, IndexError):
            return '1.0'

    @classmethod
    async def list_files(cls, doc_id: int) -> list[DocumentFileRespVo]:
        document = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if not document:
            raise ServiceException('文档不存在')
        files = await KnowledgeDocumentFileDao.list_by_doc_id(doc_id)
        return [
            DocumentFileRespVo(
                id=f.id,
                doc_id=f.doc_id,
                task_id=f.task_id,
                doc_name=f.doc_name,
                doc_type=f.doc_type,
                source_url=f.source_url,
                original_doc_key=f.original_doc_key,
                doc_key=f.doc_key,
            )
            for f in files
        ]

    @classmethod
    async def _resolve_files_for_read(
        cls,
        document: KnowledgeDocument,
        file_id: int | None = None,
        file_ids: list[int] | None = None,
        all_files: bool = False,
        *,
        for_preview: bool = False,
    ) -> list[KnowledgeDocumentFile]:
        files = await KnowledgeDocumentFileDao.list_by_doc_id(document.doc_id)
        if not files:
            raise ServiceException('文档文件不存在')

        is_crawl = document.source_type == DocumentSourceType.CRAWL.value

        if for_preview:
            if is_crawl:
                if file_id is None:
                    raise ServiceException('网页爬取文档预览须指定 file_id')
                matched = [f for f in files if f.id == file_id]
                if not matched:
                    raise ServiceException('文件不属于该文档或不存在')
                return matched
            if file_id is not None:
                matched = [f for f in files if f.id == file_id]
                if not matched:
                    raise ServiceException('文件不属于该文档或不存在')
                return matched
            if len(files) != 1:
                raise ServiceException('上传文档文件行异常，请指定 file_id')
            return files

        # download
        if all_files:
            return files
        if file_ids:
            matched = await KnowledgeDocumentFileDao.list_by_ids(file_ids, doc_id=document.doc_id)
            if len(matched) != len(set(file_ids)):
                raise ServiceException('部分文件不属于该文档或不存在')
            return matched
        if file_id is not None:
            matched = [f for f in files if f.id == file_id]
            if not matched:
                raise ServiceException('文件不属于该文档或不存在')
            return matched
        if is_crawl:
            raise ServiceException('网页爬取文档下载须指定 file_id、file_ids 或 all=1')
        if len(files) != 1:
            raise ServiceException('上传文档文件行异常，请指定 file_id')
        return files

    @classmethod
    async def _download_file_local(cls, file_row: KnowledgeDocumentFile) -> tuple[str, str]:
        if not file_row.doc_key:
            raise ServiceException('文档对象键为空')
        local = await KnowledgeMinioService.download_file(file_row.doc_key)
        filename = file_row.doc_name or f'file_{file_row.id}.md'
        if not filename.lower().endswith('.md'):
            filename = f'{filename}.md'
        return filename, local.local_path

    @classmethod
    async def txt_to_markdown(cls, model: TxtToMarkdownModel) -> str:
        return await LlmChatService.txt_to_markdown(model.content)

    @classmethod
    async def preview_document(cls, doc_id: int, file_id: int | None = None) -> str:
        document = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if not document:
            raise ServiceException('文档不存在')
        files = await cls._resolve_files_for_read(document, file_id=file_id, for_preview=True)
        _, local_path = await cls._download_file_local(files[0])
        return local_path

    @classmethod
    async def download_document(
        cls,
        doc_id: int,
        file_id: int | None = None,
        file_ids: list[int] | None = None,
        all_files: bool = False,
    ) -> tuple[str, str]:
        """
        下载文档，返回 (文件名, 本地路径)。
        多文件时打包 zip。
        """
        document = await KnowledgeDocumentDao.get_document_by_id(doc_id)
        if not document:
            raise ServiceException('文档不存在')
        files = await cls._resolve_files_for_read(
            document, file_id=file_id, file_ids=file_ids, all_files=all_files, for_preview=False
        )

        if len(files) == 1:
            return await cls._download_file_local(files[0])

        return await cls._pack_zip(document, files)

    @classmethod
    async def _pack_zip(
        cls, document: KnowledgeDocument, files: list[KnowledgeDocumentFile]
    ) -> tuple[str, str]:
        temp_dir = Path(UploadConfig.UPLOAD_TEMP_PATH)
        temp_dir.mkdir(parents=True, exist_ok=True)
        zip_name = f'{document.doc_title or document.doc_id}_files.zip'
        # 避免非法文件名字符
        safe_zip = ''.join(c if c.isalnum() or c in '._- ' else '_' for c in zip_name)
        zip_path = temp_dir / f'doc_{document.doc_id}_{safe_zip}'

        local_paths: list[str] = []
        try:
            with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
                used_names: set[str] = set()
                for file_row in files:
                    filename, local_path = await cls._download_file_local(file_row)
                    local_paths.append(local_path)
                    arcname = filename
                    if arcname in used_names:
                        stem = Path(filename).stem
                        arcname = f'{stem}_{file_row.id}.md'
                    used_names.add(arcname)
                    zf.write(local_path, arcname=arcname)
        finally:
            for p in local_paths:
                try:
                    Path(p).unlink(missing_ok=True)
                except OSError:
                    pass

        return safe_zip, str(zip_path)
