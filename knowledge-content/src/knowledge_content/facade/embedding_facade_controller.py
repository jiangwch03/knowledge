"""对外接口：canary 任务查询与 promote。分段查询只走 MCP。"""
from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel
from knowledge_common.utils.response_util import ResponseUtil

from knowledge_content.service.embedding_eval_facade_service import EmbeddingEvalFacadeService
from knowledge_common.facade.api.knowledge_content.embedding_eval_vo import (
    CanaryEmbeddingTaskItemVo,
    CompletedCanaryTaskQuery,
    EmbeddingTaskForEvalVo,
    PromoteTaskRequest,
)

embedding_facade_controller = APIRouterPro(
    prefix='/internal/embedding',
    order_num=12,
    tags=['CONTENT-Embedding-Facade'],
    dependencies=[PreAuthDependency()],
)


@embedding_facade_controller.get(
    '/canary-tasks',
    summary='分页查询已完成且仍为 canary 的向量化任务，供评测任务绑定',
    response_model=PageResponseModel[CanaryEmbeddingTaskItemVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:list')],
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
    '/tasks/{task_id}',
    summary='Embedding 任务详情（评测用）',
    response_model=DataResponseModel[EmbeddingTaskForEvalVo],
    dependencies=[UserInterfaceAuthDependency('rag:embedding:query')],
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
    dependencies=[UserInterfaceAuthDependency('rag:embedding:publish')],
)
async def promote_task(
    request: Request,
    body: PromoteTaskRequest,
) -> Response:
    await EmbeddingEvalFacadeService.promote(body.embedding_task_id)
    return ResponseUtil.success(msg='发布成功')
