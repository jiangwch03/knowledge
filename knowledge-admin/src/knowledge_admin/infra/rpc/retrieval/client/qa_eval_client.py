"""admin → knowledge-retrieval QA 评测。"""

from __future__ import annotations

from knowledge_common.common.feign import FeignDataVo, feign_client, post_mapping
from knowledge_common.config.env import RpcClientConfig
from knowledge_common.facade.api.knowledge_retrieval.qa_eval_vo import EvalQaAnswerRequestVo, EvalQaAnswerVo


@feign_client(
    name=RpcClientConfig.knowledge_retrieval_service_name,
    # 进程直接挂裸路由；APP_ROOT_PATH 只给网关和文档，直连再拼会 404
    path='',
    url=RpcClientConfig.knowledge_retrieval_url,
    # 8 题同时采数时，改写加回答经常超过 3 分钟
    timeout=360,
)
class QaEvalClient:
    """@FeignClient(name = "knowledge-retrieval")。方法体不执行。"""

    @post_mapping('/internal/qa/eval')
    async def eval_answer(cls, req: EvalQaAnswerRequestVo) -> FeignDataVo[EvalQaAnswerVo]:
        """评测采数问答"""
