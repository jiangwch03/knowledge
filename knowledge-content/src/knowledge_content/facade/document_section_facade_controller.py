"""对内接口：上传文档按标题切节。不挂登录，不写分段表。"""
from typing import Annotated

from fastapi import Path, Request, Response
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.facade.api.knowledge_content.document_section_vo import DocumentSectionListVo
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.document_section_service import DocumentSectionService

document_section_facade_controller = APIRouterPro(
    prefix='/internal/documents',
    order_num=15,
    tags=['CONTENT-DocumentSection-Facade'],
)


@document_section_facade_controller.get(
    '/{doc_id}/sections',
    summary='把上传文档的 Markdown 切成出题用的节',
    response_model=DataResponseModel[DocumentSectionListVo],
)
async def list_document_sections(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> Response:
    data = await DocumentSectionService.list_sections(doc_id)
    return ResponseUtil.success(data=data)
