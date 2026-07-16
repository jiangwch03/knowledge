from typing import Annotated

from fastapi import File, UploadFile
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.minio_service import MinioService
from knowledge_content.vo.minio_vo import (
    MinioUploadLocalReqVo,
    MinioUploadRespVo,
)

# 定义 MinIO 模块路由，prefix='/minio' 表示该模块下所有接口均以 /minio 开头
router = APIRouterPro(prefix='/minio', tags=['MinIO文件管理'])


@router.post(
    '/upload/local',
    dependencies=[UserInterfaceAuthDependency('knowledge_content:minio:upload:local')],
    response_model=DataResponseModel[MinioUploadRespVo],
)
async def upload_local_file(request: MinioUploadLocalReqVo) -> dict:
    """上传本地路径文件到 MinIO

    适用于服务器本地已有文件（如后台批量生成、第三方同步等场景），
    直接将磁盘文件上传至 MinIO 存储桶，返回桶内对象名供后续使用。

    :param request: 包含本地文件路径的请求体
    :return: 统一成功响应，data 为 MinioUploadRespVo（含 object_name）
    """
    result = await MinioService.upload_local_file(request.file_path)
    return ResponseUtil.success(data=result)


@router.post(
    '/upload/stream',
    dependencies=[UserInterfaceAuthDependency('knowledge_content:minio:upload:stream')],
    response_model=DataResponseModel[MinioUploadRespVo],
)
async def upload_stream(
    file: Annotated[UploadFile, File(..., description='前端上传的文件流')],
) -> dict:
    """上传前端文件流到 MinIO

    接收前端通过 multipart/form-data 上传的文件流，
    读取完整内容后写入 MinIO 存储桶，返回桶内对象名。

    注意：本接口会将文件完整读取到内存后上传，
    超大文件场景建议后续优化为分块/流式直传。

    :param file: FastAPI UploadFile 对象，封装了前端上传的文件流与元数据
    :return: 统一成功响应，data 为 MinioUploadRespVo（含 object_name）
    """
    # 读取上传文件的完整二进制内容到内存
    content = await file.read()
    # 取前端原始文件名，若未提供则降级为 unknown
    filename = file.filename or 'unknown'
    result = await MinioService.upload_stream(content, filename)
    return ResponseUtil.success(data=result)
