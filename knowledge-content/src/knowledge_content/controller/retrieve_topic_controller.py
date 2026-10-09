from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageModel, PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel

from knowledge_content.service.retrieve_topic_service import RetrieveTopicService
from knowledge_content.vo.retrieve_topic_vo import (
    RetrieveTopicCreateRequest,
    RetrieveTopicDetailVo,
    RetrieveTopicListItemVo,
    RetrieveTopicListQuery,
    RetrieveTopicUpdateRequest,
)

retrieve_topic_controller = APIRouterPro(
    prefix='/topic',
    order_num=18,
    tags=['CONTENT-主题'],
    dependencies=[PreAuthDependency()],
)


@retrieve_topic_controller.get(
    '/list',
    summary='主题列表',
    response_model=PageResponseModel[RetrieveTopicListItemVo],
    dependencies=[UserInterfaceAuthDependency('rag:topic:list')],
)
async def list_topics(
    request: Request,
    query: Annotated[RetrieveTopicListQuery, Query()],
) -> Response:
    page: PageModel = await RetrieveTopicService.list_topics(query)
    return ResponseUtil.success(model_content=page)


@retrieve_topic_controller.get(
    '/{topic_id}',
    summary='主题详情',
    response_model=DataResponseModel[RetrieveTopicDetailVo],
    dependencies=[UserInterfaceAuthDependency('rag:topic:query')],
)
async def get_topic(
    request: Request,
    topic_id: Annotated[int, Path(description='主题ID')],
) -> Response:
    detail: RetrieveTopicDetailVo = await RetrieveTopicService.get_topic(topic_id)
    return ResponseUtil.success(data=detail)


@retrieve_topic_controller.post(
    '',
    summary='新建主题并抽词',
    response_model=DataResponseModel[RetrieveTopicDetailVo],
    dependencies=[UserInterfaceAuthDependency('rag:topic:add')],
)
async def create_topic(
    request: Request,
    body: RetrieveTopicCreateRequest,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    detail = await RetrieveTopicService.create_topic(body, current_user)
    return ResponseUtil.success(data=detail)


@retrieve_topic_controller.put(
    '/{topic_id}',
    summary='修改主题并重抽关键词',
    response_model=DataResponseModel[RetrieveTopicDetailVo],
    dependencies=[UserInterfaceAuthDependency('rag:topic:edit')],
)
async def update_topic(
    request: Request,
    topic_id: Annotated[int, Path(description='主题ID')],
    body: RetrieveTopicUpdateRequest,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    detail = await RetrieveTopicService.update_topic(topic_id, body, current_user)
    return ResponseUtil.success(data=detail)


@retrieve_topic_controller.post(
    '/{topic_id}/retry',
    summary='重试失败的主题抽词',
    response_model=DataResponseModel[RetrieveTopicDetailVo],
    dependencies=[UserInterfaceAuthDependency('rag:topic:retry')],
)
async def retry_topic(
    request: Request,
    topic_id: Annotated[int, Path(description='主题ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    detail = await RetrieveTopicService.retry_topic(topic_id, current_user)
    return ResponseUtil.success(data=detail)


@retrieve_topic_controller.delete(
    '/{topic_id}',
    summary='软删除主题',
    dependencies=[UserInterfaceAuthDependency('rag:topic:remove')],
)
async def delete_topic(
    request: Request,
    topic_id: Annotated[int, Path(description='主题ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    await RetrieveTopicService.delete_topic(topic_id, current_user)
    return ResponseUtil.success(msg='删除成功')
