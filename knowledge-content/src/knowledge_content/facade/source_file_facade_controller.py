"""对内接口：返回文档原文的 MinIO 对象键。不挂登录，也不返回文件内容。"""
from typing import Annotated

from fastapi import Path, Request, Response
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.facade.api.knowledge_content.source_file_vo import SourceMarkdownFileListVo
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.document_source_file_service import DocumentSourceFileService

source_file_facade_controller = APIRouterPro(
    prefix='/internal/documents',
    order_num=14,
    tags=['CONTENT-SourceFile-Facade'],
)


@source_file_facade_controller.get(
    '/{doc_id}/source-files',
    summary='列出文档解析后的 Markdown 对象键',
    response_model=DataResponseModel[SourceMarkdownFileListVo],
)
async def list_source_files(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> Response:
    data = await DocumentSourceFileService.list_source_files(doc_id)
    return ResponseUtil.success(data=data)
