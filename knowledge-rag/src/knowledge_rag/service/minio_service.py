from knowledge_common.config.env import UploadConfig
from knowledge_common.utils.log_util import logger

from knowledge_rag.infra.minio.minio_client import MinioClient
from knowledge_rag.infra.minio.vo.minio_vo import MinioDownloadRespVo, MinioUploadRespVo


class MinioService:
    """MinIO 业务服务层

    负责编排 MinIO 客户端调用与业务配置（如下载路径）。
    按照项目分层规范，Controller 层通过本类间接操作 MinIO，
    禁止 Controller 直接调用 MinioClient。
    """

    def __init__(self) -> None:
        """初始化业务服务

        实例化 MinioClient 并读取 UploadConfig 中的下载根目录配置，
        所有下载操作均落在 DOWNLOAD_PATH/minio 子目录下，避免与系统其他下载文件混杂。
        """
        self._client = MinioClient()
        # 从全局配置读取下载根目录，默认值为 vf_admin/download_path
        self._download_base = UploadConfig.DOWNLOAD_PATH

    async def upload_local_file(self, file_path: str) -> MinioUploadRespVo:
        """上传本地磁盘文件到 MinIO 存储桶

        委托 MinioClient 完成实际上传，object_name 默认使用本地文件名。

        :param file_path: 本地文件路径
        :return: 包装后的上传响应 VO，包含桶内对象名
        """
        object_name = await self._client.upload_local_file(file_path)
        return MinioUploadRespVo(object_name=object_name)

    async def upload_stream(self, data: bytes, filename: str) -> MinioUploadRespVo:
        """上传内存字节流到 MinIO 存储桶

        适用于接收前端 multipart 文件后写入 MinIO 的场景。

        :param data: 文件的二进制内容
        :param filename: 原始文件名，作为桶内对象名使用
        :return: 包装后的上传响应 VO，包含桶内对象名
        """
        object_name = await self._client.upload_stream(data, filename)
        return MinioUploadRespVo(object_name=object_name)

    async def download_file(self, object_name: str) -> MinioDownloadRespVo:
        """根据桶内对象名从 MinIO 下载文件到本地

        下载目录固定为 UploadConfig.DOWNLOAD_PATH/minio，
        若该目录下已存在同名文件，则直接返回已有路径（幂等）。

        :param object_name: 桶内文件路径（上传接口返回的对象名）
        :return: 包装后的下载响应 VO，包含本地文件绝对路径
        """
        # 拼接下载子目录，确保 MinIO 下载文件与其他业务下载隔离
        download_dir = f'{self._download_base}/minio'
        local_path = await self._client.download_file(object_name, download_dir)
        return MinioDownloadRespVo(local_path=local_path)
