"""admin 从知识库桶读取对象。出题只下载解析后的 Markdown。"""
from __future__ import annotations

import asyncio
from pathlib import Path

from knowledge_common.config.env import MinioConfig, UploadConfig
from knowledge_common.utils.log_util import logger

from knowledge_admin.infra.minio.minio_client import MinioClient


class KnowledgeMinioService:
    """绑定 knowledge_bucket_name，按对象键读取 UTF-8 文本。"""

    _client = MinioClient()
    _bucket = MinioConfig.knowledge_bucket_name
    _download_dir = f'{UploadConfig.DOWNLOAD_PATH}/{MinioConfig.minio_download_subdir}'

    @classmethod
    async def download_content(cls, object_name: str) -> str:
        """按桶内对象键读取全文。本地已有同名文件则直接读，否则先从 MinIO 下载。"""
        local_path = await cls._client.download_file(object_name, cls._download_dir, cls._bucket)
        return await asyncio.to_thread(Path(local_path).read_text, encoding='utf-8')

    @classmethod
    async def delete_cached_files(cls, object_names: list[str]) -> int:
        """删掉这些对象键对应的本地缓存文件。目录和其他文件不动。"""
        return await asyncio.to_thread(cls._delete_cached_files, object_names)

    @classmethod
    def _delete_cached_files(cls, object_names: list[str]) -> int:
        root = Path(cls._download_dir).resolve()
        removed = 0
        for name in object_names:
            if not name.strip():
                continue
            path = cls._client.cache_path(name, cls._download_dir, cls._bucket).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                continue
            path.unlink()
            removed += 1
            logger.info('已删除本地下载缓存: {}', path)
        return removed
