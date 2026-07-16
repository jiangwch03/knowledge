from typing import Annotated

from fastapi import Path, Query, Request, Response
from fastapi.responses import FileResponse
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.crawler_document_service import CrawlerDocumentService
from knowledge_content.service.document_service import DocumentService
from knowledge_content.vo.crawler_vo import (
    CrawlerDocumentListQueryVo,
    CrawlerDocumentRespVo,
)


crawler_document_controller = APIRouterPro(
    prefix='/crawler/document', order_num=5, tags=['CONTENT-网页爬虫-文档'], dependencies=[PreAuthDependency()]
)


@crawler_document_controller.get(
    '/list',
    summary='爬取文档列表',
    description='查询指定爬取任务关联的文档列表',
    response_model=PageResponseModel[CrawlerDocumentRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:document:list')],
)
async def get_document_list(
    request: Request,
    query: Annotated[CrawlerDocumentListQueryVo, Query()],
) -> Response:
    """查询爬取结果文档列表"""
    result = await CrawlerDocumentService.get_documents_by_task(
        task_id=query.task_id,
        page_num=query.page_num,
        page_size=query.page_size,
        status=query.status,
        create_by=query.create_by,
        del_flag=query.del_flag,
    )
    return ResponseUtil.success(model_content=result)


@crawler_document_controller.get(
    '/{doc_id}/preview',
    summary='预览爬取文档',
    description='预览爬取结果 Markdown 内容',
    dependencies=[UserInterfaceAuthDependency('rag:crawler:document:preview')],
)
async def preview_document(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> FileResponse:
    """预览爬取文档"""
    local_path = await DocumentService.preview_document(doc_id)
    return FileResponse(
        path=local_path,
        media_type='text/markdown',
        content_disposition_type='inline',
    )


@crawler_document_controller.get(
    '/{doc_id}/download',
    summary='下载爬取文档',
    description='下载爬取结果 Markdown 文件',
    dependencies=[UserInterfaceAuthDependency('rag:crawler:document:download')],
)
async def download_document(
    request: Request,
    doc_id: Annotated[int, Path(description='文档ID')],
) -> FileResponse:
    """下载爬取文档"""
    filename, local_path = await DocumentService.download_document(doc_id)
    return FileResponse(
        path=local_path,
        media_type='application/octet-stream',
        filename=filename,
    )
