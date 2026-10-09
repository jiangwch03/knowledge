from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel

from knowledge_admin.service.eval_dataset_service import EvalDatasetService
from knowledge_admin.vo.eval_vo import (
    EvalDatasetCreateVo,
    EvalDatasetDetailVo,
    EvalDatasetItemModel,
    EvalDatasetItemPageQueryModel,
    EvalDatasetItemUpdateVo,
    EvalDatasetModel,
    EvalDatasetPageQueryModel,
)

eval_dataset_controller = APIRouterPro(
    prefix='/rag/eval/dataset',
    order_num=40,
    tags=['知识库-测评集'],
    dependencies=[PreAuthDependency()],
)


@eval_dataset_controller.get(
    '/list',
    summary='测评集分页列表',
    response_model=PageResponseModel[EvalDatasetModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:dataset:list')],
)
async def list_datasets(
    request: Request,
    query: Annotated[EvalDatasetPageQueryModel, Query()],
) -> Response:
    result = await EvalDatasetService.list_datasets(query, is_page=True)
    logger.info('测评集列表查询成功')
    return ResponseUtil.success(model_content=result)


@eval_dataset_controller.post(
    '',
    summary='创建测评集并启动生成',
    response_model=DataResponseModel[EvalDatasetModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:dataset:create')],
)
@Log(title='测评集', business_type=BusinessType.INSERT)
async def create_dataset(
    request: Request,
    body: EvalDatasetCreateVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    data = await EvalDatasetService.create_dataset(body, current_user)
    return ResponseUtil.success(data=data, msg='创建成功，生成任务已启动')


@eval_dataset_controller.get(
    '/{dataset_id}',
    summary='测评集详情（含题目）',
    response_model=DataResponseModel[EvalDatasetDetailVo],
    dependencies=[UserInterfaceAuthDependency('rag:eval:dataset:query')],
)
async def get_dataset(
    request: Request,
    dataset_id: Annotated[int, Path(description='测评集ID')],
) -> Response:
    data = await EvalDatasetService.get_dataset_detail(dataset_id)
    return ResponseUtil.success(data=data)


@eval_dataset_controller.get(
    '/{dataset_id}/items',
    summary='测评集题目分页',
    response_model=PageResponseModel[EvalDatasetItemModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:dataset:query')],
)
async def list_items(
    request: Request,
    dataset_id: Annotated[int, Path(description='测评集ID')],
    query: Annotated[EvalDatasetItemPageQueryModel, Query()],
) -> Response:
    query.dataset_id = dataset_id
    result = await EvalDatasetService.list_items(query, is_page=True)
    return ResponseUtil.success(model_content=result)


@eval_dataset_controller.put(
    '/item/{item_id}',
    summary='编辑题目（问题/标准答案/是否计入测评）',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:eval:dataset:edit')],
)
@Log(title='测评集题目', business_type=BusinessType.UPDATE)
async def update_item(
    request: Request,
    item_id: Annotated[int, Path(description='题目ID')],
    body: EvalDatasetItemUpdateVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await EvalDatasetService.update_item(item_id, body, current_user)
    return ResponseUtil.success(msg=result.message)
