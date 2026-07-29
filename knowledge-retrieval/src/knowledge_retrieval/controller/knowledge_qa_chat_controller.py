from typing import Annotated

from fastapi import Path, Query, Request, Response
from fastapi.responses import StreamingResponse

from knowledge_common.agent.service.agent_message_service import AgentMessageService
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel
from knowledge_common.config.env import AiModelFunctionAdapterConfig
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.agents.service.knowledge_qa_agent_service import KnowledgeQaAgentService
from knowledge_retrieval.vo.knowledge_qa_vo import ChatMessageVo, MessageListQueryVo, MessageRespVo

knowledge_qa_chat_controller = APIRouterPro(
    prefix='/qa/chat',
    order_num=3,
    tags=['RETRIEVAL-知识问答-聊天'],
    dependencies=[PreAuthDependency()],
)


@knowledge_qa_chat_controller.get(
    '/models',
    summary='知识问答可用模型',
    response_model=DataResponseModel[list[AiModelConfigModel]],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:chat')],
)
async def get_models(request: Request) -> Response:
    result = await AiModelFunctionAdapterDao.get_adapters_by_param_id(
        AiModelFunctionAdapterConfig.knowledge_qa_agent_param_id
    )
    return ResponseUtil.success(data=result)


@knowledge_qa_chat_controller.post(
    '/{session_id}/message',
    summary='发送聊天消息（SSE）',
    response_class=StreamingResponse,
    responses={200: {'description': 'SSE', 'content': {'text/event-stream': {}}}},
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:chat')],
)
async def send_message(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    vo: ChatMessageVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> StreamingResponse:
    return StreamingResponse(
        KnowledgeQaAgentService.stream_chat(session_id=session_id, vo=vo, current_user=current_user),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@knowledge_qa_chat_controller.get(
    '/{session_id}/messages',
    summary='历史消息列表',
    response_model=PageResponseModel[MessageRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:chat')],
)
async def get_message_list(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    query: Annotated[MessageListQueryVo, Query()],
) -> Response:
    result = await AgentMessageService.get_messages(
        session_id=session_id,
        page_num=query.page_num,
        page_size=query.page_size,
    )
    return ResponseUtil.success(model_content=result)
