from urllib.parse import urlparse

from knowledge_common.config.env import MinioConfig, UploadConfig

from knowledge_content.infra.minio.minio_client import MinioClient
from knowledge_content.infra.minio.vo.minio_vo import MinioDownloadRespVo, MinioUploadRespVo


class MinioService:
    """MinIO 业务服务层（类方法）

    负责编排 MinIO 客户端调用与业务配置（如下载路径）。
    按照项目分层规范，Controller 层通过本类间接操作 MinIO，
    禁止 Controller 直接调用 MinioClient。

    所有方法均为类方法，MinioClient 全局单例共享，避免业务代码频繁创建/销毁实例。
    默认绑定 minio_bucket_name，子类 KnowledgeMinioService 绑定 knowledge_bucket_name。
    """

    _client = MinioClient()
    _bucket = MinioConfig.minio_bucket_name
    _download_base = UploadConfig.DOWNLOAD_PATH

    @classmethod
    async def upload_local_file(cls, file_path: str, object_name: str | None = None) -> MinioUploadRespVo:
        """上传本地磁盘文件到 MinIO 存储桶

        委托 MinioClient 完成实际上传，object_name 默认使用本地文件名，也可显式指定桶内路径。

        :param file_path: 本地文件路径
        :param object_name: 桶内对象路径（可选），为 None 时使用本地文件名
        :return: 包装后的上传响应 VO，包含桶内对象名
        """
        object_name = await cls._client.upload_local_file(file_path, object_name, cls._bucket)
        return MinioUploadRespVo(object_name=object_name)

    @classmethod
    async def upload_stream(cls, data: bytes, filename: str) -> MinioUploadRespVo:
        """上传内存字节流到 MinIO 存储桶

        适用于接收前端 multipart 文件后写入 MinIO 的场景。

        :param data: 文件的二进制内容
        :param filename: 原始文件名，作为桶内对象名使用
        :return: 包装后的上传响应 VO，包含桶内对象名
        """
        object_name = await cls._client.upload_stream(data, filename, cls._bucket)
        return MinioUploadRespVo(object_name=object_name)

    @classmethod
    def get_object_url(cls, object_name: str) -> str:
        """根据桶内对象名构造访问 URL

        :param object_name: 文件在桶内的存储路径（对象名）
        :return: 对象访问 URL
        """
        return cls._client.get_object_url(object_name, cls._bucket)

    @classmethod
    def parse_object_name(cls, object_url: str) -> str:
        """从 MinIO 对象 URL 中提取 object_name

        URL 格式：{scheme}://{netloc}/{bucket}/{object_name}
        通过 urlparse 解析 path，再去除 bucket 前缀，避免硬编码 split 逻辑。

        :param object_url: MinIO 对象访问 URL
        :return: 桶内对象路径（object_name）
        """
        parsed = urlparse(object_url)
        path = parsed.path.lstrip('/')
        if path.startswith(cls._bucket + '/'):
            return path[len(cls._bucket) + 1:]
        return path

    @classmethod
    async def download_content(cls, object_name: str) -> str:
        """从 MinIO 读取对象内容为字符串（内存中读取，不落盘）

        :param object_name: 桶内对象路径
        :return: 文件内容的 UTF-8 字符串
        """
        data = await cls._client.get_object(object_name, cls._bucket)
        return data.decode('utf-8')

    @classmethod
    async def download_content_prefix(cls, object_name: str, max_chars: int) -> tuple[str, bool]:
        """按 Range 仅拉取对象前缀，避免大文件整对象进内存。

        UTF-8 最坏 4 字节/字符，按 max_chars * 4 拉取；末尾不完整码点丢弃后
        再按字符截断。返回 (样本文本, 是否截断)。

        :param object_name: 桶内对象路径
        :param max_chars: 需要的最大字符数
        :return: (样本文本, 是否因上限截断)
        """
        if max_chars <= 0:
            return '', True
        # UTF-8 单字符最多 4 字节
        max_bytes: int = max_chars * 4
        data: bytes = await cls._client.get_object(
            object_name, cls._bucket, length=max_bytes
        )
        # Range 可能截在多字节字符中间，忽略尾部不完整码点
        text: str = data.decode('utf-8', errors='ignore')
        truncated: bool = len(data) >= max_bytes or len(text) > max_chars
        return text[:max_chars], truncated

    @classmethod
    async def download_file(cls, object_name: str) -> MinioDownloadRespVo:
        """根据桶内对象名从 MinIO 下载文件到本地

        下载目录固定为 UploadConfig.DOWNLOAD_PATH/{minio_download_subdir}，
        若该目录下已存在同名文件，则直接返回已有路径（幂等）。

        :param object_name: 桶内文件路径（上传接口返回的对象名）
        :return: 包装后的下载响应 VO，包含本地文件绝对路径
        """
        # 拼接下载子目录，确保 MinIO 下载文件与其他业务下载隔离
        download_dir = f'{cls._download_base}/{MinioConfig.minio_download_subdir}'
        local_path = await cls._client.download_file(object_name, download_dir, cls._bucket)
        return MinioDownloadRespVo(local_path=local_path)


class KnowledgeMinioService(MinioService):
    """知识库专用 MinIO 业务服务层

    继承 MinioService 的所有类方法，仅替换目标桶为 knowledge_bucket_name。
    业务代码无需传入 bucket，直接调用 KnowledgeMinioService.xxx() 即可。
    """

    _bucket = MinioConfig.knowledge_bucket_name

class MilvusMinioService(MinioService):
    """milvus专用 MinIO 业务服务层

    继承 MinioService 的所有类方法，仅替换目标桶为 knowledge_bucket_name。
    业务代码无需传入 bucket，直接调用 MilvusMinioService.xxx() 即可。
    """

    _bucket = MinioConfig.milvus_bucket_name

__all__ = [
    'KnowledgeMinioService',
    'MilvusMinioService',
]