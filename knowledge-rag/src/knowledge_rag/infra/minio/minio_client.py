from __future__ import annotations

import asyncio
import threading
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio
from knowledge_common.config.env import MinioConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger



class MinioClient:
    """MinIO 客户端封装（单例）

    基于 minio 官方 SDK 封装，提供异步上传/下载能力。
    所有同步阻塞的 SDK 方法均通过 asyncio.to_thread 转入线程池执行，
    避免阻塞主事件循环。

    全局共享同一个底层 Minio SDK 客户端实例，避免业务代码频繁创建/销毁连接。
    各操作通过 bucket_name 参数指定目标桶，为 None 时使用配置中的默认桶。
    """

    _instance: MinioClient | None = None
    _lock = threading.Lock()

    def __new__(cls) -> MinioClient:
        """保证全局只有一个 MinioClient 实例"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """初始化 MinIO 客户端实例（仅首次调用会创建底层客户端）"""
        if hasattr(self, '_client'):
            return
        self._config = MinioConfig
        # 解析地址，提取 host:port，去除 scheme
        parsed = urlparse(self._config.minio_address)
        endpoint = f'{parsed.hostname}:{parsed.port}' if parsed.port else str(parsed.hostname)
        # 初始化底层同步 MinIO 客户端
        self._client = Minio(
            endpoint=endpoint,
            access_key=self._config.minio_access_key_id,
            secret_key=self._config.minio_secret_access_key,
            secure=self._config.minio_use_ssl,
        )

    async def upload_local_file(
        self,
        file_path: str,
        object_name: str | None = None,
        bucket_name: str | None = None,
    ) -> str:
        """上传本地磁盘文件到 MinIO 存储桶

        若未指定 object_name，则默认使用本地文件的文件名（含后缀）。
        若 bucket 中已存在同名 object_name，新文件会直接覆盖旧文件。

        :param file_path: 本地文件的绝对路径或相对路径
        :param object_name: 文件在桶内的存储路径（对象名），为 None 时取本地文件名
        :param bucket_name: 目标存储桶名称，为 None 时使用配置中的默认桶 minio_bucket_name
        :return: 上传成功后返回的 object_name，业务方需保存该值以便后续下载
        :raises ServiceException: 文件不存在、路径非文件、或 MinIO 上传失败时抛出
        """
        bucket = bucket_name or self._config.minio_bucket_name
        path = Path(file_path)
        # 前置校验：路径必须存在且为普通文件
        if not path.exists():
            raise ServiceException(f'文件不存在: {file_path}')
        if not path.is_file():
            raise ServiceException(f'路径不是文件: {file_path}')

        # 未显式指定对象名时，使用本地文件的原文件名
        if object_name is None:
            object_name = path.name

        try:
            # fput_object 是同步阻塞方法，通过 to_thread 在线程池中执行
            # 使用 lambda 包装零参函数，避免 ParamSpec 中间可选参数推导断裂误报
            await asyncio.to_thread(
                lambda: self._client.fput_object(bucket, object_name, str(path))
            )
            logger.info(f'本地文件上传至 MinIO 成功: object_name={object_name}, bucket={bucket}')
        except Exception as e:
            logger.error(f'本地文件上传至 MinIO 失败: object_name={object_name}, error={e}')
            raise ServiceException(f'本地文件上传至 MinIO 失败: {e}') from e

        return object_name

    async def upload_stream(
        self,
        data: bytes,
        object_name: str,
        bucket_name: str | None = None,
    ) -> str:
        """上传内存中的字节流到 MinIO 存储桶

        适用于接收前端 UploadFile 后读取 content 再转发的场景。
        内部将 bytes 包装为 BytesIO 流，满足 minio SDK 对 file-like object 的要求。

        :param data: 文件的完整二进制内容（已通过 await file.read() 等方式读取到内存）
        :param object_name: 文件在桶内的存储路径（对象名）
        :param bucket_name: 目标存储桶名称，为 None 时使用配置中的默认桶 minio_bucket_name
        :return: 上传成功后返回的 object_name
        :raises ServiceException: MinIO 上传失败时抛出
        """
        bucket = bucket_name or self._config.minio_bucket_name
        try:
            # put_object 需要 file-like object 和明确的 content length
            # BytesIO 实现了 read() 方法，可直接作为 data 参数传入
            stream = BytesIO(data)
            await asyncio.to_thread(
                lambda: self._client.put_object(bucket, object_name, stream, len(data))
            )
            logger.info(f'文件流上传至 MinIO 成功: object_name={object_name}, bucket={bucket}, size={len(data)}')
        except Exception as e:
            logger.error(f'文件流上传至 MinIO 失败: object_name={object_name}, error={e}')
            raise ServiceException(f'文件流上传至 MinIO 失败: {e}') from e

        return object_name

    def get_object_url(self, object_name: str, bucket_name: str | None = None) -> str:
        """构造 MinIO 对象的访问 URL

        基于配置的 minio_address 与 bucket 拼接出可公开访问的对象 URL。

        :param object_name: 文件在桶内的存储路径（对象名）
        :param bucket_name: 目标存储桶名称，为 None 时使用配置中的默认桶 minio_bucket_name
        :return: 对象访问 URL
        """
        bucket = bucket_name or self._config.minio_bucket_name
        # 兼容 object_name 已包含 bucket 前缀的情况（如旧数据）
        object_name = self._strip_bucket_prefix(object_name, bucket)
        parsed = urlparse(self._config.minio_address)
        scheme = parsed.scheme or 'http'
        netloc = parsed.netloc or parsed.hostname or 'localhost'
        if parsed.port and ':' not in netloc:
            netloc = f'{netloc}:{parsed.port}'
        return f'{scheme}://{netloc}/{bucket}/{object_name}'

    @staticmethod
    def _strip_bucket_prefix(object_name: str, bucket: str) -> str:
        """去除 object_name 中已包含的 bucket 前缀，防止 S3 路径重复

        数据库中可能存储了包含 bucket 前缀的 object_name（如 knowledge-data/documents/...），
        而 S3 SDK 调用 fget_object(bucket, object_name) 时会自动拼接 bucket，
        导致实际请求路径变为 bucket/bucket/object_name（重复），触发 NoSuchKey 错误。

        :param object_name: 桶内对象路径
        :param bucket: 目标桶名称
        :return: 去除 bucket 前缀后的 object_name
        """
        prefix = f'{bucket}/'
        if object_name.startswith(prefix):
            return object_name[len(prefix):]
        return object_name

    async def download_file(
        self,
        object_name: str,
        download_dir: str,
        bucket_name: str | None = None,
    ) -> str:
        """从 MinIO 存储桶下载文件到本地指定目录

        下载前会检查目标路径是否已存在同名文件：
        - 若存在，直接返回已有本地路径，避免重复下载（幂等性）
        - 若不存在，从 MinIO 拉取并写入本地

        当 object_name 包含 '/' 层级（如 docs/report.pdf）时，
        本地目录会自动创建对应的子目录结构。

        :param object_name: 文件在桶内的存储路径（对象名），上传接口返回的值
        :param download_dir: 文件下载到本地的根目录，如 vf_admin/download_path/minio
        :param bucket_name: 目标存储桶名称，为 None 时使用配置中的默认桶 minio_bucket_name
        :return: 文件在本地磁盘上的绝对路径
        :raises ServiceException: MinIO 下载失败时抛出
        """
        bucket = bucket_name or self._config.minio_bucket_name
        # 兼容 object_name 已包含 bucket 前缀的情况（如旧数据）
        object_name = self._strip_bucket_prefix(object_name, bucket)
        target_dir = Path(download_dir)
        # 确保下载根目录存在，不存在则递归创建
        target_dir.mkdir(parents=True, exist_ok=True)
        # 本地目标路径 = 下载根目录 / 桶内对象路径
        local_path = target_dir / object_name

        # 幂等性检查：若文件已下载过，直接返回已有路径，不再请求 MinIO
        if local_path.exists():
            logger.info(f'文件已存在于本地，跳过下载: local_path={local_path}')
            return str(local_path)

        # 若 object_name 包含子目录（如 a/b/c.pdf），需提前创建中间目录
        local_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # fget_object 是同步阻塞方法，通过 to_thread 在线程池中执行
            # 使用 lambda 包装零参函数，避免 ParamSpec 中间可选参数推导断裂误报
            await asyncio.to_thread(
                lambda: self._client.fget_object(bucket, object_name, str(local_path))
            )
            logger.info(f'文件从 MinIO 下载成功: object_name={object_name}, local_path={local_path}')
        except Exception as e:
            logger.error(f'文件从 MinIO 下载失败: object_name={object_name}, error={e}')
            raise ServiceException(f'文件从 MinIO 下载失败: {e}') from e

        return str(local_path)
