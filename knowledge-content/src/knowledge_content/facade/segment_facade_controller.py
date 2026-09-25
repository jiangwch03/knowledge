"""对内接口：按文档分页返回分段正文，供 admin 测评集生成拉取。不挂登录，也不挂菜单权限。"""
from typing import Annotated

from fastapi import Query, Request, Response
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import PageResponseModel
from knowledge_common.facade.api.knowledge_content.segment_facade_vo import (
    SegmentFullItemVo,
    SegmentListQuery,
)
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.document_segment_query_service import DocumentSegmentQueryService

segment_facade_controller = APIRouterPro(
    prefix='/internal/segments',
    order_num=13,
    tags=['CONTENT-Segment-Facade'],
)


@segment_facade_controller.get(
    '',
    summary='按文档分页返回分段正文',
    response_model=PageResponseModel[SegmentFullItemVo],
)
async def list_full_segments(
    request: Request,
    query: Annotated[SegmentListQuery, Query()],
) -> Response:
    page = await DocumentSegmentQueryService.list_full_segments(query)
    return ResponseUtil.success(model_content=page)
