"""调用 knowledge-retrieval 评测 Client，统一日志与异常。"""

from __future__ import annotations

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.facade.api.knowledge_retrieval.qa_eval_vo import EvalQaAnswerRequestVo, EvalQaAnswerVo
from knowledge_common.utils.log_util import logger

from knowledge_admin.infra.rpc.biz_result import ensure_business_ok
from knowledge_admin.infra.rpc.retrieval.client.qa_eval_client import QaEvalClient


class QaEvalService:
    """评测非流式采数。"""

    @classmethod
    async def eval_answer(cls, req: EvalQaAnswerRequestVo) -> EvalQaAnswerVo:
        """按题问答并带回检索上下文。"""
        loc = f'{cls.__name__}.eval_answer'
        try:
            body = await QaEvalClient.eval_answer(req)
            ensure_business_ok(body.code, body.msg, loc=loc)
            if body.data is None:
                raise ServiceException(message=f'[{loc}] 评测采数问答失败: 返回数据为空')
            result = body.data
        except ServiceException:
            raise
        except Exception as e:
            logger.exception(
                '[{}] 评测采数问答失败 task_id={} release_tag={} error={}',
                loc,
                req.task_id,
                req.release_tag,
                e,
            )
            raise ServiceException(message=f'[{loc}] 评测采数问答失败: {e}') from e
        logger.info(
            '[{}] 评测采数问答成功 task_id={} release_tag={} q={}',
            loc,
            req.task_id,
            req.release_tag,
            (req.question or '')[:64],
        )
        return result
