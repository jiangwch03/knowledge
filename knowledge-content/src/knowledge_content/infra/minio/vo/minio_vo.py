from pydantic import BaseModel, Field


class MinioUploadRespVo(BaseModel):
    """MinIO 上传响应 VO

    上传成功后返回给调用方的核心数据，业务系统应将该 object_name 持久化存储，
    后续下载、删除、预览等操作均依赖此值定位桶内文件。
    """

    object_name: str = Field(
        ...,
        description='文件在 MinIO 桶内的存储路径（对象名），例如 "reports/2024/summary.pdf" 或 "image.png"',
    )


class MinioDownloadRespVo(BaseModel):
    """MinIO 下载响应 VO

    下载完成后返回给调用方，包含文件落盘后的本地绝对路径，
    业务系统可直接使用该路径进行后续本地文件操作（如解析、转码等）。
    """

    local_path: str = Field(
        ...,
        description='文件下载到本地磁盘后的绝对路径，例如 "/project/vf_admin/download_path/minio/reports/summary.pdf"',
    )
