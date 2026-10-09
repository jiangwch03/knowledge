from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel

from knowledge_admin.service.eval_task_service import EvalTaskService
from knowledge_admin.vo.eval_vo import (
    EvalRunModel,
    EvalRunPageQueryModel,
    EvalRunReportVo,
    EvalTaskCreateVo,
    EvalTaskListItemModel,
    EvalTaskModel,
    EvalTaskPageQueryModel,
    EvalTaskSwapDatasetVo,
)

eval_task_controller = APIRouterPro(
    prefix='/rag/eval/task',
    order_num=41,
    tags=['知识库-测评任务'],
    dependencies=[PreAuthDependency()],
)


@eval_task_controller.get(
    '/list',
    summary='测评任务分页列表',
    response_model=PageResponseModel[EvalTaskListItemModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:list')],
)
async def list_tasks(
    request: Request,
    query: Annotated[EvalTaskPageQueryModel, Query()],
) -> Response:
    result = await EvalTaskService.list_tasks(query, is_page=True)
    return ResponseUtil.success(model_content=result)


@eval_task_controller.post(
    '',
    summary='创建测评任务',
    response_model=DataResponseModel[EvalTaskModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:create')],
)
@Log(title='测评任务', business_type=BusinessType.INSERT)
async def create_task(
    request: Request,
    body: EvalTaskCreateVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    data = await EvalTaskService.create_task(body, current_user)
    return ResponseUtil.success(data=data, msg='创建成功')


@eval_task_controller.get(
    '/{eval_task_id}',
    summary='测评任务详情',
    response_model=DataResponseModel[EvalTaskModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:query')],
)
async def get_task(
    request: Request,
    eval_task_id: Annotated[int, Path(description='测评任务ID')],
) -> Response:
    data = await EvalTaskService.get_task(eval_task_id)
    return ResponseUtil.success(data=data)


@eval_task_controller.put(
    '/{eval_task_id}/dataset',
    summary='更换绑定测评集（OPEN）',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:create')],
)
@Log(title='测评任务换集', business_type=BusinessType.UPDATE)
async def swap_dataset(
    request: Request,
    eval_task_id: Annotated[int, Path(description='测评任务ID')],
    body: EvalTaskSwapDatasetVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await EvalTaskService.swap_dataset(eval_task_id, body, current_user)
    return ResponseUtil.success(msg=result.message)


@eval_task_controller.post(
    '/{eval_task_id}/run',
    summary='启动评测 run',
    response_model=DataResponseModel[EvalRunModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:run')],
)
@Log(title='测评 run', business_type=BusinessType.OTHER)
async def start_run(
    request: Request,
    eval_task_id: Annotated[int, Path(description='测评任务ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    launch = await EvalTaskService.start_run(eval_task_id, current_user)
    return ResponseUtil.success(data=launch.run, msg=launch.message)


@eval_task_controller.get(
    '/{eval_task_id}/runs',
    summary='run 列表',
    response_model=PageResponseModel[EvalRunModel],
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:query')],
)
async def list_runs(
    request: Request,
    eval_task_id: Annotated[int, Path(description='测评任务ID')],
    query: Annotated[EvalRunPageQueryModel, Query()],
) -> Response:
    query.eval_task_id = eval_task_id
    result = await EvalTaskService.list_runs(query, is_page=True)
    return ResponseUtil.success(model_content=result)


@eval_task_controller.get(
    '/run/{run_id}/report',
    summary='run 报告（汇总+逐题）',
    response_model=DataResponseModel[EvalRunReportVo],
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:query')],
)
async def get_report(
    request: Request,
    run_id: Annotated[int, Path(description='run ID')],
) -> Response:
    data = await EvalTaskService.get_report(run_id)
    return ResponseUtil.success(data=data)


@eval_task_controller.post(
    '/{eval_task_id}/publish',
    summary='发布 canary→prod 并归档',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:eval:task:publish')],
)
@Log(title='测评发布', business_type=BusinessType.UPDATE)
async def publish(
    request: Request,
    eval_task_id: Annotated[int, Path(description='测评任务ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await EvalTaskService.publish(eval_task_id, current_user)
    return ResponseUtil.success(msg=result.message)
