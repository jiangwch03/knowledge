from typing import Annotated

from fastapi import Query, Request, Response
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.crawler_document_service import CrawlerDocumentService
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
        doc_title=query.doc_title,
        status=query.status,
        create_by=query.create_by,
        del_flag=query.del_flag,
    )
    return ResponseUtil.success(model_content=result)
