from typing import Annotated

from fastapi import Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel
from knowledge_common.agent.service.agent_message_service import AgentMessageService
from knowledge_common.config.env import AiModelFunctionAdapterConfig
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_content.agents.service.crawler_agent_service import CrawlerAgentService
from knowledge_content.vo.crawler_vo import ChatMessageVo, MessageListQueryVo, MessageRespVo, ResumeVo

web_crawler_chat_controller = APIRouterPro(
    prefix='/crawler/chat', order_num=7, tags=['CONTENT-网页爬虫-聊天'], dependencies=[PreAuthDependency()]
)


@web_crawler_chat_controller.get(
    '/models',
    summary='获取网页爬取Agent可用模型列表',
    description='返回 web_crawler_agent 功能适配点下启用的模型列表',
    response_model=DataResponseModel[list[AiModelConfigModel]],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:chat')],
)
async def get_crawler_models(
    request: Request,
) -> Response:
    """查询网页爬取Agent可用的模型列表"""
    result = await AiModelFunctionAdapterDao.get_adapters_by_param_id(
        AiModelFunctionAdapterConfig.crawler_agent_param_id
    )
    return ResponseUtil.success(data=result)


@web_crawler_chat_controller.post(
    '/{session_id}/message',
    summary='发送聊天消息（SSE）',
    description='向 Agent 发送消息并以 SSE 流式返回 Agent 的分析过程与结果',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': 'SSE 流式返回 Agent 响应',
            'content': {
                'text/event-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('rag:crawler:chat')],
)
async def send_message(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    vo: ChatMessageVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> StreamingResponse:
    """发送聊天消息，SSE 流式返回 Agent 响应"""
    return StreamingResponse(
        CrawlerAgentService.stream_chat(session_id=session_id, vo=vo, current_user=current_user),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@web_crawler_chat_controller.post(
    '/{session_id}/resume',
    summary='恢复中断（SSE）',
    description='用户对中断弹框（如 URL 路由审批）做出决策后，恢复 Agent 图执行，以 SSE 流式返回后续分析结果。后续所有中断审批逻辑均在此接口中扩展。',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': 'SSE 流式返回 Agent 响应',
            'content': {
                'text/event-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('rag:crawler:chat')],
)
async def resume_agent(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    vo: ResumeVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> StreamingResponse:
    """恢复中断，SSE 流式返回 Agent 响应"""
    return StreamingResponse(
        CrawlerAgentService.stream_resume(session_id=session_id, vo=vo, current_user=current_user),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@web_crawler_chat_controller.get(
    '/{session_id}/messages',
    summary='历史消息列表',
    description='分页查询指定会话的历史消息',
    response_model=PageResponseModel[MessageRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:chat')],
)
async def get_message_list(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    query: Annotated[MessageListQueryVo, Query()],
) -> Response:
    """查询会话历史消息"""
    result = await AgentMessageService.get_messages(
        session_id=session_id,
        page_num=query.page_num,
        page_size=query.page_size,
    )
    return ResponseUtil.success(model_content=result)
