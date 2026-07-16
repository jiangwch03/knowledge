from pydantic import BaseModel, Field


class MinioUploadLocalReqVo(BaseModel):
    """本地文件上传请求 VO

    用于将服务器本地磁盘上的文件直接上传到 MinIO 存储桶。
    适用于后台任务、批量导入等已有本地文件的场景。
    """

    file_path: str = Field(
        ...,
        description='本地文件的绝对路径或相对路径，例如 "/data/upload/report.pdf"',
    )


class MinioUploadRespVo(BaseModel):
    """上传响应 VO

    上传成功后返回给前端或上游服务的统一数据结构，
    核心字段 object_name 是后续所有操作的唯一标识。
    """

    object_name: str = Field(
        ...,
        description='文件在 MinIO 桶内的存储路径（对象名），后续下载、删除均需使用此值',
    )
