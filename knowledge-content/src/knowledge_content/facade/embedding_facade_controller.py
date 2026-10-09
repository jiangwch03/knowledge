"""对内接口：canary 任务查询与 promote。不挂登录，也不挂菜单权限。"""
from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.embedding_eval_facade_service import EmbeddingEvalFacadeService
from knowledge_common.facade.api.knowledge_content.embedding_eval_vo import (
    CanaryEmbeddingTaskItemVo,
    CompletedCanaryTaskQuery,
    ContentLabelListVo,
    ContentLabelQuery,
    EmbeddingTaskForEvalVo,
    PromoteTaskRequest,
)

embedding_facade_controller = APIRouterPro(
    prefix='/internal/embedding',
    order_num=12,
    tags=['CONTENT-Embedding-Facade'],
)


@embedding_facade_controller.get(
    '/canary-tasks',
    summary='分页查询已完成且仍为 canary 的向量化任务，供评测任务绑定',
    response_model=PageResponseModel[CanaryEmbeddingTaskItemVo],
)
async def list_canary_tasks(
    request: Request,
    query: Annotated[CompletedCanaryTaskQuery, Query()],
) -> Response:
    page = await EmbeddingEvalFacadeService.list_completed_canary_tasks(
        doc_id=query.doc_id,
        page_num=query.page_num,
        page_size=query.page_size,
    )
    return ResponseUtil.success(model_content=page)


@embedding_facade_controller.get(
    '/labels',
    summary='批量查询文档标题和向量化切分策略名，供测评任务列表展示',
    response_model=DataResponseModel[ContentLabelListVo],
)
async def list_content_labels(
    request: Request,
    query: Annotated[ContentLabelQuery, Query()],
) -> Response:
    data = await EmbeddingEvalFacadeService.list_content_labels(query)
    return ResponseUtil.success(data=data)


@embedding_facade_controller.get(
    '/tasks/{task_id}',
    summary='Embedding 任务详情（评测用）',
    response_model=DataResponseModel[EmbeddingTaskForEvalVo],
)
async def get_task_for_eval(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
) -> Response:
    data = await EmbeddingEvalFacadeService.get_task_for_eval(task_id)
    return ResponseUtil.success(data=data)


@embedding_facade_controller.post(
    '/promote',
    summary='发布 canary→prod（仅评测编排调用）',
    response_model=DataResponseModel[None],
)
async def promote_task(
    request: Request,
    body: PromoteTaskRequest,
) -> Response:
    await EmbeddingEvalFacadeService.promote(body.embedding_task_id)
    return ResponseUtil.success(msg='发布成功')
