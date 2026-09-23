"""对外接口：评测非流式问答采数。"""
from typing import Annotated

from fastapi import Request, Response
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.agents.service.knowledge_qa_agent_service import KnowledgeQaAgentService
from knowledge_retrieval.vo.qa_eval_vo import EvalAnswerRequestVo, EvalAnswerRespVo

qa_eval_controller = APIRouterPro(
    prefix='/internal/qa',
    order_num=4,
    tags=['RETRIEVAL-评测Facade'],
    dependencies=[PreAuthDependency()],
)


@qa_eval_controller.post(
    '/eval',
    summary='评测非流式问答（answer + contexts）',
    response_model=DataResponseModel[EvalAnswerRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:chat')],
)
async def eval_answer(
    request: Request,
    vo: EvalAnswerRequestVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result: EvalAnswerRespVo = await KnowledgeQaAgentService.eval_answer(vo, current_user)
    return ResponseUtil.success(data=result)
