"""调用 knowledge-content embedding Client，统一日志与异常。"""

from __future__ import annotations

from knowledge_common.common.feign import FeignPageVo
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_content.embedding_eval_vo import (
    CanaryEmbeddingTaskItemVo,
    CompletedCanaryTaskQuery,
    ContentLabelListVo,
    ContentLabelQuery,
    EmbeddingTaskForEvalVo,
    PromoteTaskRequest,
)
from knowledge_common.utils.log_util import logger

from knowledge_admin.infra.rpc.biz_result import ensure_business_ok
from knowledge_admin.infra.rpc.content.client.embedding_client import EmbeddingClient


class EmbeddingService:
    """embedding 对内接口。"""

    @classmethod
    async def list_canary_tasks(
        cls, query: CompletedCanaryTaskQuery
    ) -> FeignPageVo[CanaryEmbeddingTaskItemVo]:
        """分页查询已完成且仍为 canary 的向量化任务。"""
        loc = f'{cls.__name__}.list_canary_tasks'
        try:
            page = await EmbeddingClient.list_canary_tasks(query)
            ensure_business_ok(page.code, page.msg, loc=loc)
        except ServiceException:
            raise
        except Exception as e:
            logger.exception(
                '[{}] 分页查询 canary 向量化任务失败 doc_id={} page={}/{} error={}',
                loc,
                query.doc_id,
                query.page_num,
                query.page_size,
                e,
            )
            raise ServiceException(message=f'[{loc}] 分页查询 canary 向量化任务失败: {e}') from e
        logger.info(
            '[{}] 分页查询 canary 向量化任务成功 doc_id={} page={}/{} total={}',
            loc,
            query.doc_id,
            query.page_num,
            query.page_size,
            page.total,
        )
        return page

    @classmethod
    async def list_content_labels(cls, query: ContentLabelQuery) -> ContentLabelListVo:
        """批量查询文档标题和向量化切分策略名。"""
        loc = f'{cls.__name__}.list_content_labels'
        try:
            body = await EmbeddingClient.list_content_labels(query)
            ensure_business_ok(body.code, body.msg, loc=loc)
            if body.data is None:
                raise ServiceException(message=f'[{loc}] 查询展示名称失败: 返回数据为空')
            data = body.data
        except ServiceException:
            raise
        except Exception as e:
            logger.exception('[{}] 查询展示名称失败 error={}', loc, e)
            raise ServiceException(message=f'[{loc}] 查询展示名称失败: {e}') from e
        logger.info(
            '[{}] 查询展示名称成功 documents={} tasks={}',
            loc,
            len(data.documents),
            len(data.embedding_tasks),
        )
        return data

    @classmethod
    async def get_embedding_task(cls, task_id: int) -> EmbeddingTaskForEvalVo:
        """按 ID 查询 embedding 任务详情。"""
        loc = f'{cls.__name__}.get_embedding_task'
        try:
            body = await EmbeddingClient.get_embedding_task(task_id)
            ensure_business_ok(body.code, body.msg, loc=loc)
            if body.data is None:
                raise ServiceException(message=f'[{loc}] 查询 embedding 任务详情失败: 返回数据为空')
            data = body.data
        except ServiceException:
            raise
        except Exception as e:
            logger.exception('[{}] 查询 embedding 任务详情失败 task_id={} error={}', loc, task_id, e)
            raise ServiceException(message=f'[{loc}] 查询 embedding 任务详情失败: {e}') from e
        logger.info('[{}] 查询 embedding 任务详情成功 task_id={}', loc, task_id)
        return data

    @classmethod
    async def promote(cls, req: PromoteTaskRequest) -> None:
        """发布 canary → prod。"""
        loc = f'{cls.__name__}.promote'
        try:
            ack = await EmbeddingClient.promote(req)
            ensure_business_ok(ack.code, ack.msg, loc=loc)
        except ServiceException:
            raise
        except Exception as e:
            logger.exception(
                '[{}] 发布 canary→prod 失败 embedding_task_id={} error={}',
                loc,
                req.embedding_task_id,
                e,
            )
            raise ServiceException(message=f'[{loc}] 发布 canary→prod 失败: {e}') from e
        logger.info('[{}] 发布 canary→prod 成功 embedding_task_id={}', loc, req.embedding_task_id)
