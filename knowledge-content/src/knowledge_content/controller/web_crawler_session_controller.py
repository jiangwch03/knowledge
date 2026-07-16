from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.agent.enums.agent_type_enum import AgentType
from knowledge_common.agent.service.agent_session_service import AgentSessionService
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.data_scope import DataScopeDependency
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.mapper.do.agent_session_do import AgentSession
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.user_vo import CurrentUserModel
from pydantic_validation_decorator import ValidateFields
from sqlalchemy import ColumnElement

from knowledge_content.vo.crawler_vo import (
    CreateSessionVo,
    RenameSessionVo,
    SessionListQueryVo,
    SessionRespVo,
)

CRAWLER_AGENT_TYPE = AgentType.WEB_CRAWLER.value

web_crawler_session_controller = APIRouterPro(
    prefix='/crawler/session', order_num=8, tags=['CONTENT-网页爬虫-会话'], dependencies=[PreAuthDependency()]
)


@web_crawler_session_controller.get(
    '/list',
    summary='会话列表',
    description='分页查询当前用户的网页爬取会话列表',
    response_model=PageResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:list')],
)
async def get_session_list(
    request: Request,
    query: Annotated[SessionListQueryVo, Query()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """查询当前用户的会话列表（仅查本人）"""
    result = await AgentSessionService.get_session_list(
        agent_type=CRAWLER_AGENT_TYPE,
        user_id=current_user.user.user_id,
        title=query.title,
        is_page=True,
        page_num=query.page_num,
        page_size=query.page_size,
    )
    return ResponseUtil.success(model_content=result)


@web_crawler_session_controller.get(
    '/list-all',
    summary='会话列表（数据权限）',
    description='按数据权限范围分页查询会话列表，用于任务/文档筛选下拉',
    response_model=PageResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:list')],
)
async def get_session_list_all(
    request: Request,
    query: Annotated[SessionListQueryVo, Query()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(AgentSession)],
) -> Response:
    """按数据权限范围查询会话列表（用于任务/文档筛选）"""
    result = await AgentSessionService.get_session_list(
        agent_type=CRAWLER_AGENT_TYPE,
        user_id=current_user.user.user_id,
        title=query.title,
        is_page=True,
        page_num=query.page_num,
        page_size=query.page_size,
        data_scope_sql=data_scope_sql,
    )
    return ResponseUtil.success(model_content=result)


@web_crawler_session_controller.post(
    '',
    summary='创建会话',
    description='新建一个网页爬取分析会话',
    response_model=DataResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:add')],
)
@ValidateFields(validate_model='create_session')
@Log(title='网页爬虫-会话', business_type=BusinessType.INSERT)
async def create_session(
    request: Request,
    vo: CreateSessionVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """创建新的网页爬取会话"""
    session = await AgentSessionService.create_session(
        agent_type=CRAWLER_AGENT_TYPE,
        session_title=vo.session_title,
        model_id=vo.model_id,
        user_id=current_user.user.user_id,
        dept_id=current_user.user.dept_id,
        create_by=current_user.user.user_name,
    )
    return ResponseUtil.success(data=session)


@web_crawler_session_controller.get(
    '/{session_id}',
    summary='会话详情',
    description='获取指定会话的详细信息',
    response_model=DataResponseModel[SessionRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:query')],
)
async def get_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
) -> Response:
    """获取会话详情"""
    session = await AgentSessionService.get_session_vo(session_id, agent_type=CRAWLER_AGENT_TYPE)
    return ResponseUtil.success(data=session)


@web_crawler_session_controller.put(
    '/{session_id}/rename',
    summary='重命名会话',
    description='修改会话标题',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:edit')],
)
@ValidateFields(validate_model='rename_session')
@Log(title='网页爬虫-会话', business_type=BusinessType.UPDATE)
async def rename_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    vo: RenameSessionVo,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """重命名会话"""
    await AgentSessionService.rename_session(
        session_id,
        vo.session_title,
        update_by=current_user.user.user_name,
        agent_type=CRAWLER_AGENT_TYPE,
    )
    return ResponseUtil.success(msg='重命名成功')


@web_crawler_session_controller.put(
    '/{session_id}/close',
    summary='关闭会话',
    description='关闭指定会话，不再接受新消息',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:edit')],
)
@Log(title='网页爬虫-会话', business_type=BusinessType.UPDATE)
async def close_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """关闭会话"""
    await AgentSessionService.close_session(
        session_id,
        update_by=current_user.user.user_name,
        agent_type=CRAWLER_AGENT_TYPE,
    )
    return ResponseUtil.success(msg='关闭成功')


@web_crawler_session_controller.delete(
    '/{session_id}',
    summary='删除会话',
    description='级联软删除会话及其消息记录',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:session:remove')],
)
@Log(title='网页爬虫-会话', business_type=BusinessType.DELETE)
async def delete_session(
    request: Request,
    session_id: Annotated[int, Path(description='会话ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """删除会话及关联消息"""
    await AgentSessionService.delete_session(
        session_id,
        update_by=current_user.user.user_name,
        agent_type=CRAWLER_AGENT_TYPE,
    )
    return ResponseUtil.success(msg='删除成功')
