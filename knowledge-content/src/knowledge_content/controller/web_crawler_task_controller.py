from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.aspect.data_scope import DataScopeDependency
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_common.utils.response_util import ResponseUtil
from sqlalchemy import ColumnElement

from knowledge_content.enums.crawl_task_error_code_enum import CrawlTaskErrorCode
from knowledge_content.enums.crawl_task_status_enum import CrawlTaskStatus
from knowledge_content.mapper.do.web_crawler_task_do import WebCrawlerTask
from knowledge_common.exceptions.exception import ServiceException
from knowledge_content.service.web_crawler_task_service import WebCrawlerTaskService
from knowledge_content.vo.crawler_vo import (
    CrawlTaskListQueryVo,
    CrawlTaskRespVo,
    EnumOption,
    UrlRecordListQueryVo,
    UrlRecordRespVo,
)

crawl_task_controller = APIRouterPro(
    prefix='/crawler/task', order_num=6, tags=['CONTENT-网页爬虫-任务'], dependencies=[PreAuthDependency()]
)


@crawl_task_controller.get(
    '/list',
    summary='任务列表',
    description='分页查询爬取任务列表',
    response_model=PageResponseModel[CrawlTaskRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:list')],
)
async def get_task_list(
    request: Request,
    query: Annotated[CrawlTaskListQueryVo, Query()],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
    data_scope_sql: Annotated[ColumnElement, DataScopeDependency(WebCrawlerTask)],
) -> Response:
    """查询爬取任务列表（按数据权限过滤）"""
    result = await WebCrawlerTaskService.get_task_list_services(
        user_id=current_user.user.user_id,
        status=query.status,
        create_by=query.create_by,
        is_page=True,
        page_num=query.page_num,
        page_size=query.page_size,
        data_scope_sql=data_scope_sql,
    )
    return ResponseUtil.success(model_content=result)


@crawl_task_controller.get(
    '/status-options',
    summary='获取任务状态选项',
    description='返回爬取任务状态枚举列表，用于前端下拉框',
    response_model=DataResponseModel[list[EnumOption]],
)
async def get_task_status_options() -> Response:
    """返回任务状态枚举列表，前端可直接用于下拉框"""
    options = [
        EnumOption(
            value=status.value,
            label=status.label,
        )
        for status in CrawlTaskStatus
    ]
    return ResponseUtil.success(data=options)


@crawl_task_controller.get(
    '/error-code-options',
    summary='获取错误码选项',
    description='返回爬取任务错误码枚举列表，用于前端下拉框',
    response_model=DataResponseModel[list[EnumOption]],
)
async def get_error_code_options() -> Response:
    """返回错误码枚举列表，前端可直接用于下拉框"""
    options = [
        EnumOption(
            value=code.value,
            label=code.label,
            type=code.type,
        )
        for code in CrawlTaskErrorCode
    ]
    return ResponseUtil.success(data=options)


@crawl_task_controller.get(
    '/{task_id}',
    summary='任务详情',
    description='获取指定爬取任务的详细信息（含进度）',
    response_model=DataResponseModel[CrawlTaskRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:query')],
)
async def get_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
) -> Response:
    """获取任务详情"""
    task = await WebCrawlerTaskService.get_task(task_id)
    return ResponseUtil.success(data=CrawlTaskRespVo.model_validate(task))


@crawl_task_controller.get(
    '/{task_id}/url-records',
    summary='获取任务URL记录',
    description='分页查询指定爬取任务的URL记录（成功爬取的URL列表）',
    response_model=PageResponseModel[UrlRecordRespVo],
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:query')],
)
async def get_url_records(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
    query: Annotated[UrlRecordListQueryVo, Query()],
) -> Response:
    """获取任务URL记录"""
    records = await WebCrawlerTaskService.get_url_records_by_task(
        task_id=task_id,
        page_num=query.page_num,
        page_size=query.page_size,
        status=query.status,
    )
    return ResponseUtil.success(model_content=records)


@crawl_task_controller.post(
    '/{task_id}/pause',
    summary='暂停任务',
    description='暂停正在执行的爬取任务',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:pause')],
)
async def pause_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
) -> Response:
    """暂停爬取任务"""
    try:
        await WebCrawlerTaskService.pause_task(task_id)
        return ResponseUtil.success(msg='已发送暂停指令，任务将在当前页面爬取完成后暂停')
    except ServiceException as e:
        return ResponseUtil.failure(msg=e.message)


@crawl_task_controller.post(
    '/{task_id}/resume',
    summary='恢复任务',
    description='恢复已暂停的爬取任务，继续爬取剩余URL',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:resume')],
)
async def resume_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """恢复爬取任务"""
    try:
        await WebCrawlerTaskService.resume_task(task_id, update_by=current_user.user.user_name)
        return ResponseUtil.success(msg='已发送恢复指令，任务将继续爬取')
    except ServiceException as e:
        return ResponseUtil.failure(msg=e.message)


@crawl_task_controller.post(
    '/{task_id}/merge',
    summary='合并已爬内容',
    description='放弃失败的URL，将已成功爬取的页面提交到文档合并队列（异步落库）',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:merge')],
)
async def merge_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
) -> Response:
    """合并已爬内容"""
    try:
        result = await WebCrawlerTaskService.merge_crawl_results(task_id)
        return ResponseUtil.success(msg=result)
    except ServiceException as e:
        return ResponseUtil.failure(msg=e.message)


@crawl_task_controller.delete(
    '/{task_id}',
    summary='删除任务',
    description='删除指定爬取任务（软删除）',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('rag:crawler:task:remove')],
)
async def delete_task(
    request: Request,
    task_id: Annotated[int, Path(description='任务ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    """删除爬取任务"""
    await WebCrawlerTaskService.delete_task(task_id, update_by=current_user.user.user_name)
    return ResponseUtil.success(msg='已删除任务')

