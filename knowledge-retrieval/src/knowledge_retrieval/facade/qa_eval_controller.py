"""对内接口：评测非流式问答采数。不挂登录，请求只带 userId，接口内再查用户。"""
from fastapi import Request, Response
from knowledge_common.common.context import RequestContext
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel
from knowledge_common.service.login_user_service import LoginUserService
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_retrieval.agents.service.knowledge_qa_agent_service import KnowledgeQaAgentService
from knowledge_retrieval.vo.qa_eval_vo import EvalAnswerRequestVo, EvalAnswerRespVo

qa_eval_controller = APIRouterPro(
    prefix='/internal/qa',
    order_num=4,
    tags=['RETRIEVAL-评测Facade'],
)


@qa_eval_controller.post(
    '/eval',
    summary='评测非流式问答（answer + contexts）',
    response_model=DataResponseModel[EvalAnswerRespVo],
)
async def eval_answer(
    request: Request,
    vo: EvalAnswerRequestVo,
) -> Response:
    caller = await LoginUserService.load_by_user_id(vo.user_id)
    token = RequestContext.set_current_user(caller)
    try:
        result: EvalAnswerRespVo = await KnowledgeQaAgentService.eval_answer(vo, caller)
    finally:
        RequestContext.reset_current_user(token)
    return ResponseUtil.success(data=result)
