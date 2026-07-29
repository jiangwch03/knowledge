from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.agent.enums.agent_type_enum import AgentType
from knowledge_common.agent.service.agent_session_service import AgentSessionService
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel
from pydantic_validation_decorator import ValidateFields

from knowledge_retrieval.vo.knowledge_qa_vo import (
    CreateSessionVo,
    RenameSessionVo,
    SessionListQueryVo,
    SessionRespVo,
)

QA_AGENT_TYPE = AgentType.KNOWLEDGE_QA.value

knowledge_qa_session_controller = APIRouterPro(
    prefix='/qa/session',
    order_num=2,
    tags=['RETRIEVAL-知识问答-会话'],
    dependencies=[PreAuthDependency()],
)


@knowledge_qa_session_controller.get(
    '/list',
    summary='会话列表',
    response_model=PageResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:session:list')],
)
async def get_session_list(
    request: Request,
    query: Annotated[SessionListQueryVo, Query()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await AgentSessionService.get_session_list(
        agent_type=QA_AGENT_TYPE,
        user_id=current_user.user.user_id,
        title=query.title,
        is_page=True,
        page_num=query.page_num,
        page_size=query.page_size,
    )
    return ResponseUtil.success(model_content=result)


@knowledge_qa_session_controller.post(
    '',
    summary='创建会话',
    response_model=DataResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:session:add')],
)
@ValidateFields(validate_model='create_session')
@Log(title='知识问答-会话', business_type=BusinessType.INSERT)
async def create_session(
    request: Request,
    vo: CreateSessionVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    session = await AgentSessionService.create_session(
        agent_type=QA_AGENT_TYPE,
        session_title=vo.session_title,
        model_id=vo.model_id,
        user_id=current_user.user.user_id,
        dept_id=current_user.user.dept_id,
        create_by=current_user.user.user_name,
    )
    return ResponseUtil.success(data=session)


@knowledge_qa_session_controller.get(
    '/{session_id}',
    summary='会话详情',
    response_model=DataResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:session:query')],
)
async def get_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
) -> Response:
    session = await AgentSessionService.get_session_vo(session_id, agent_type=QA_AGENT_TYPE)
    return ResponseUtil.success(data=session)


@knowledge_qa_session_controller.put(
    '/{session_id}/rename',
    summary='重命名会话',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:session:edit')],
)
@ValidateFields(validate_model='rename_session')
@Log(title='知识问答-会话', business_type=BusinessType.UPDATE)
async def rename_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    vo: RenameSessionVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    await AgentSessionService.rename_session(
        session_id,
        vo.session_title,
        update_by=current_user.user.user_name,
        agent_type=QA_AGENT_TYPE,
    )
    return ResponseUtil.success(msg='重命名成功')


@knowledge_qa_session_controller.put(
    '/{session_id}/close',
    summary='关闭会话',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:session:edit')],
)
@Log(title='知识问答-会话', business_type=BusinessType.UPDATE)
async def close_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    await AgentSessionService.close_session(
        session_id,
        update_by=current_user.user.user_name,
        agent_type=QA_AGENT_TYPE,
    )
    return ResponseUtil.success(msg='关闭成功')


@knowledge_qa_session_controller.delete(
    '/{session_id}',
    summary='删除会话',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:retrieve:session:remove')],
)
@Log(title='知识问答-会话', business_type=BusinessType.DELETE)
async def delete_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    await AgentSessionService.delete_session(
        session_id,
        update_by=current_user.user.user_name,
        agent_type=QA_AGENT_TYPE,
    )
    return ResponseUtil.success(msg='删除成功')
