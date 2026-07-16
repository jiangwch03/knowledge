from typing import Annotated

from fastapi import Path, Query, Request, Response
from fastapi.responses import FileResponse
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.utils.file_util import FileUtil
from knowledge_common.utils.response_util import ResponseUtil
from pydantic_validation_decorator import ValidateFields
from starlette.background import BackgroundTask

from knowledge_content.service.document_service import DocumentService
from knowledge_content.vo.document_vo import DocumentFileRespVo, TxtToMarkdownModel

document_controller = APIRouterPro(
    prefix='/document', order_num=10, tags=['CONTENT-资料管理'], dependencies=[PreAuthDependency()]
)


@document_controller.post(
    '/txt/convert',
    summary='TXT 转 Markdown',
    description='将 UTF-8 文本通过大模型转换为 Markdown',
    response_model=DataResponseModel[str],
    dependencies=[UserInterfaceAuthDependency('rag:document:txt:convert')],
)
@ValidateFields(validate_model='txt_to_markdown')
async def txt_to_markdown(
    request: Request,
    convert_model: TxtToMarkdownModel,
) -> Response:
    result = await DocumentService.txt_to_markdown(convert_model)
    return ResponseUtil.success(data=result)


@document_controller.get(
    '/{doc_id}/files',
    summary='文档文件列表',
    description='查询 knowledge_document_file 未删除行，供选页预览/下载',
    response_model=DataResponseModel[list[DocumentFileRespVo]],
    dependencies=[UserInterfaceAuthDependency('rag:document:preview')],
)
async def list_document_files(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> Response:
    files = await DocumentService.list_files(doc_id)
    return ResponseUtil.success(data=files)


@document_controller.get(
    '/{doc_id}/preview',
    summary='预览文档',
    description='从 MinIO 读取 Markdown；上传可省略 file_id，爬取必填',
    dependencies=[UserInterfaceAuthDependency('rag:document:preview')],
)
async def preview_document(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
    file_id: Annotated[int | None, Query(alias='fileId', description='文件行ID（爬取必填）')] = None,
) -> FileResponse:
    local_path = await DocumentService.preview_document(doc_id, file_id=file_id)
    return FileResponse(
        path=local_path,
        media_type='text/markdown',
        content_disposition_type='inline',
        background=BackgroundTask(FileUtil.clean_temp_file, local_path),
    )


@document_controller.get(
    '/{doc_id}/download',
    summary='下载文档',
    description='单文件或 zip；爬取须传 file_id / file_ids / all',
    dependencies=[UserInterfaceAuthDependency('rag:document:download')],
)
async def download_document(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
    file_id: Annotated[int | None, Query(alias='fileId', description='单文件行ID')] = None,
    file_ids: Annotated[str | None, Query(alias='fileIds', description='多文件ID，逗号分隔')] = None,
    all: Annotated[bool, Query(description='下载该文档全部文件为 zip')] = False,
) -> FileResponse:
    parsed_ids: list[int] | None = None
    if file_ids:
        try:
            parsed_ids = [int(x.strip()) for x in file_ids.split(',') if x.strip()]
        except ValueError as e:
            from knowledge_common.exceptions.exception import ServiceException

            raise ServiceException('file_ids 格式错误') from e

    filename, local_path = await DocumentService.download_document(
        doc_id, file_id=file_id, file_ids=parsed_ids, all_files=all
    )
    media = 'application/zip' if filename.lower().endswith('.zip') else 'application/octet-stream'
    return FileResponse(
        path=local_path,
        media_type=media,
        filename=filename,
        background=BackgroundTask(FileUtil.clean_temp_file, local_path),
    )
