from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageModel, PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel
from pydantic_validation_decorator import ValidateFields

from knowledge_content.service.embedding_model_service import EmbeddingModelService
from knowledge_content.service.embedding_preview_service import EmbeddingPreviewService
from knowledge_content.service.embedding_strategy_service import EmbeddingStrategyService
from knowledge_content.service.embedding_task_service import EmbeddingTaskService
from knowledge_content.vo.embedding_vo import (
    EmbeddingCreateTaskRequest,
    EmbeddingCreateTaskRespVo,
    EmbeddingModelInfoVo,
    EmbeddingPreviewRequest,
    EmbeddingPreviewRespVo,
    EmbeddingSegmentListQuery,
    EmbeddingSegmentVo,
    EmbeddingStrategyVo,
    EmbeddingTaskDetailVo,
    EmbeddingTaskListItemVo,
    EmbeddingTaskListQuery,
)

embedding_controller = APIRouterPro(
    prefix='/embedding',
    order_num=11,
    tags=['CONTENT-Embedding'],
    dependencies=[PreAuthDependency()],
)


@embedding_controller.get(
    '/strategies',
    summary='切分策略列表',
    description='返回五策略元数据（code/name/summary/paramSchema 等）',
    response_model=DataResponseModel[list[EmbeddingStrategyVo]],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:query')],
)
async def list_strategies(request: Request) -> Response:
    return ResponseUtil.success(data=await EmbeddingStrategyService.list_strategies())


@embedding_controller.get(
    '/model-info',
    summary='Embedding 模型信息',
    description='只读；来自 document_embedding 业务适配',
    response_model=DataResponseModel[EmbeddingModelInfoVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:query')],
)
async def get_model_info(request: Request) -> Response:
    info: EmbeddingModelInfoVo = await EmbeddingModelService.get_model_info()
    return ResponseUtil.success(data=info)


@embedding_controller.post(
    '/preview',
    summary='切分预览',
    description='样本截断预览，不写库、不 embed',
    response_model=DataResponseModel[EmbeddingPreviewRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:create')],
)
@ValidateFields(validate_model='preview_request')
async def preview_split(
    request: Request,
    preview_request: EmbeddingPreviewRequest,
) -> Response:
    result: EmbeddingPreviewRespVo = await EmbeddingPreviewService.preview(preview_request)
    return ResponseUtil.success(data=result)


@embedding_controller.post(
    '/tasks',
    summary='创建 Embedding 任务',
    description='校验文档状态；存在进行中或未发布(canary)任务时拒绝，须先删除',
    response_model=DataResponseModel[EmbeddingCreateTaskRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:create')],
)
@ValidateFields(validate_model='create_request')
async def create_task(
    request: Request,
    create_request: EmbeddingCreateTaskRequest,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result: EmbeddingCreateTaskRespVo = await EmbeddingTaskService.create_task(create_request, current_user)
    return ResponseUtil.success(data=result)


@embedding_controller.get(
    '/tasks',
    summary='Embedding 任务列表',
    description='分页查询任务列表',
    response_model=PageResponseModel[EmbeddingTaskListItemVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:list')],
)
async def list_tasks(
    request: Request,
    query: Annotated[EmbeddingTaskListQuery, Query()],
) -> Response:
    page: PageModel = await EmbeddingTaskService.list_tasks(query)
    return ResponseUtil.success(model_content=page)


@embedding_controller.get(
    '/tasks/{task_id}',
    summary='Embedding 任务详情',
    response_model=DataResponseModel[EmbeddingTaskDetailVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:query')],
)
async def get_task_detail(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
) -> Response:
    detail: EmbeddingTaskDetailVo = await EmbeddingTaskService.get_task_detail(task_id)
    return ResponseUtil.success(data=detail)


@embedding_controller.get(
    '/tasks/{task_id}/segments',
    summary='任务分段列表',
    description='分页查看切分效果',
    response_model=PageResponseModel[EmbeddingSegmentVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:query')],
)
async def list_task_segments(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
    query: Annotated[EmbeddingSegmentListQuery, Query()],
) -> Response:
    page: PageModel = await EmbeddingTaskService.list_task_segments(task_id, query)
    return ResponseUtil.success(model_content=page)


@embedding_controller.post(
    '/tasks/{task_id}/retry',
    summary='重试失败任务',
    description='仅 CHUNK_FAILED / EMBED_FAILED 可重试；不改切分参数，按失败阶段回到 CHUNKING / EMBEDDING',
    response_model=DataResponseModel[EmbeddingCreateTaskRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:retry')],
)
async def retry_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result: EmbeddingCreateTaskRespVo = await EmbeddingTaskService.retry_task(task_id, current_user)
    return ResponseUtil.success(data=result)


@embedding_controller.delete(
    '/tasks/{task_id}',
    summary='删除 Embedding 任务',
    description='可删进行中/失败/未发布(canary)；已发布(prod)不可删。删除后同文档才可新建任务',
    response_model=DataResponseModel[None],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:remove')],
)
async def delete_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    await EmbeddingTaskService.delete_task(task_id, current_user)
    return ResponseUtil.success(msg='删除成功')
