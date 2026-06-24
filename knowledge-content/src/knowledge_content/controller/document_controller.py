from typing import Annotated

from fastapi import Path, Query, Request, Response
from fastapi.responses import FileResponse
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.utils.response_util import ResponseUtil
from pydantic_validation_decorator import ValidateFields

from knowledge_content.service.document_service import DocumentService
from knowledge_content.vo.document_vo import TxtToMarkdownModel

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
    '/{doc_id}/preview',
    summary='预览文档',
    description='从 MinIO 读取 Markdown 内容',
    dependencies=[UserInterfaceAuthDependency('rag:document:preview')],
)
async def preview_document(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> FileResponse:
    local_path = await DocumentService.preview_document(doc_id)
    return FileResponse(
        path=local_path,
        media_type='text/markdown',
        content_disposition_type='inline',
    )


@document_controller.get(
    '/{doc_id}/download',
    summary='下载文档',
    description='以流形式下载 Markdown 文件',
    dependencies=[UserInterfaceAuthDependency('rag:document:download')],
)
async def download_document(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> FileResponse:
    filename, local_path = await DocumentService.download_document(doc_id)
    """
    FileResponse 底层走操作系统 sendfile 系统调用，零拷贝直接从磁盘发到 socket，几乎不占 Python 进程内存
    """
    return FileResponse(
        path=local_path,
        media_type='application/octet-stream',
        filename=filename,
    )
