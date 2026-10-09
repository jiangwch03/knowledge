"""admin → knowledge-content embedding facade。"""

from __future__ import annotations

from knowledge_common.common.feign import FeignAckVo, FeignDataVo, FeignPageVo, feign_client, get_mapping, post_mapping
from knowledge_common.config.env import RpcClientConfig
from knowledge_common.facade.api.knowledge_content.embedding_eval_vo import (
    CanaryEmbeddingTaskItemVo,
    CompletedCanaryTaskQuery,
    ContentLabelListVo,
    ContentLabelQuery,
    EmbeddingTaskForEvalVo,
    PromoteTaskRequest,
)


@feign_client(
    name=RpcClientConfig.knowledge_content_service_name,
    # 进程直接挂裸路由；APP_ROOT_PATH 只给网关和文档，直连再拼会 404
    path='',
    url=RpcClientConfig.knowledge_content_url,
    timeout=120,
)
class EmbeddingClient:
    """@FeignClient(name = "knowledge-content")。方法体不执行。"""

    @get_mapping('/internal/embedding/canary-tasks')
    async def list_canary_tasks(
        cls, query: CompletedCanaryTaskQuery
    ) -> FeignPageVo[CanaryEmbeddingTaskItemVo]:
        """分页查询已完成且仍为 canary 的向量化任务"""

    @get_mapping('/internal/embedding/labels')
    async def list_content_labels(cls, query: ContentLabelQuery) -> FeignDataVo[ContentLabelListVo]:
        """批量查询文档标题和向量化切分策略名"""

    @get_mapping('/internal/embedding/tasks/{task_id}')
    async def get_embedding_task(cls, task_id: int) -> FeignDataVo[EmbeddingTaskForEvalVo]:
        """查询 embedding 任务详情"""

    @post_mapping('/internal/embedding/promote')
    async def promote(cls, req: PromoteTaskRequest) -> FeignAckVo:
        """发布 canary→prod"""
