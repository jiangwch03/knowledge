from typing import Annotated

from fastapi import Query, Request, Response
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageModel, PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel

from knowledge_content.service.topic_everyday_word_service import TopicEverydayWordService
from knowledge_content.vo.topic_everyday_word_vo import (
    TopicEverydayWordAddRequest,
    TopicEverydayWordQuery,
    TopicEverydayWordRemoveRequest,
    TopicEverydayWordVo,
)

topic_everyday_word_controller = APIRouterPro(
    prefix='/everyday-word',
    order_num=17,
    tags=['CONTENT-日常词'],
    dependencies=[PreAuthDependency()],
)


@topic_everyday_word_controller.get(
    '/list',
    summary='日常词列表',
    response_model=PageResponseModel[TopicEverydayWordVo],
    dependencies=[UserInterfaceAuthDependency('rag:everyday:list')],
)
async def list_everyday_words(
    request: Request,
    query: Annotated[TopicEverydayWordQuery, Query()],
) -> Response:
    page: PageModel = await TopicEverydayWordService.list_words(query)
    return ResponseUtil.success(model_content=page)


@topic_everyday_word_controller.post(
    '/add',
    summary='新增日常词',
    response_model=DataResponseModel[TopicEverydayWordVo],
    dependencies=[UserInterfaceAuthDependency('rag:everyday:add')],
)
async def add_everyday_word(
    request: Request,
    body: TopicEverydayWordAddRequest,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    saved = await TopicEverydayWordService.add_word(body, current_user)
    return ResponseUtil.success(msg='已加入日常词', data=saved)


@topic_everyday_word_controller.post(
    '/init',
    summary='初始化日常词',
    dependencies=[UserInterfaceAuthDependency('rag:everyday:init')],
)
async def initialize_everyday_words(
    request: Request,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    total = await TopicEverydayWordService.initialize_words(current_user)
    return ResponseUtil.success(msg=f'已重新入库 {total} 条日常词')


@topic_everyday_word_controller.post(
    '/remove',
    summary='剔除日常词',
    dependencies=[UserInterfaceAuthDependency('rag:everyday:remove')],
)
async def remove_everyday_words(
    request: Request,
    body: TopicEverydayWordRemoveRequest,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    removed = await TopicEverydayWordService.remove_words(body, current_user)
    return ResponseUtil.success(msg=f'已剔除 {removed} 个日常词')
