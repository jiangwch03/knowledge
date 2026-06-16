from datetime import datetime
from typing import Annotated

from fastapi import Form, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from knowledge_common.common.annotation.cache_annotation import ApiCache, ApiCacheEvict
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.annotation.rate_limit_annotation import ApiRateLimit, ApiRateLimitPreset
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.constant import ApiGroup, ApiNamespace
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.vo.post_vo import DeletePostModel, PostModel, PostPageQueryModel
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_common.utils.common_util import bytes2file_response
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.response_util import ResponseUtil
from pydantic_validation_decorator import ValidateFields

from knowledge_admin.service.post_service import PostService

post_controller = APIRouterPro(
    prefix='/system/post', order_num=7, tags=['系统管理-岗位管理'], dependencies=[PreAuthDependency()]
)


@post_controller.get(
    '/list',
    summary='获取岗位分页列表接口',
    description='用于获取岗位分页列表',
    response_model=PageResponseModel[PostModel],
    dependencies=[UserInterfaceAuthDependency('system:post:list')],
)
@ApiCache(namespace=ApiNamespace.SYSTEM_POST_LIST)
async def get_system_post_list(
    request: Request,
    post_page_query: Annotated[PostPageQueryModel, Query()],
) -> Response:
    # 获取分页数据
    post_page_query_result = await PostService.get_post_list_services(post_page_query, is_page=True)
    logger.info('获取成功')

    return ResponseUtil.success(model_content=post_page_query_result)


@post_controller.post(
    '',
    summary='新增岗位接口',
    description='用于新增岗位',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:post:add')],
)
@ValidateFields(validate_model='add_post')
@ApiCacheEvict(namespaces=ApiGroup.POST_MUTATION)
@Log(title='岗位管理', business_type=BusinessType.INSERT)
async def add_system_post(
    request: Request,
    add_post: PostModel,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    add_post.create_by = current_user.user.user_name
    add_post.create_time = datetime.now()
    add_post.update_by = current_user.user.user_name
    add_post.update_time = datetime.now()
    add_post_result = await PostService.add_post_services(add_post)
    logger.info(add_post_result.message)

    return ResponseUtil.success(msg=add_post_result.message)


@post_controller.put(
    '',
    summary='编辑岗位接口',
    description='用于编辑岗位',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:post:edit')],
)
@ValidateFields(validate_model='edit_post')
@ApiCacheEvict(namespaces=ApiGroup.POST_MUTATION)
@Log(title='岗位管理', business_type=BusinessType.UPDATE)
async def edit_system_post(
    request: Request,
    edit_post: PostModel,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_post.update_by = current_user.user.user_name
    edit_post.update_time = datetime.now()
    edit_post_result = await PostService.edit_post_services(edit_post)
    logger.info(edit_post_result.message)

    return ResponseUtil.success(msg=edit_post_result.message)


@post_controller.delete(
    '/{post_ids}',
    summary='删除岗位接口',
    description='用于删除岗位',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('system:post:remove')],
)
@ApiCacheEvict(namespaces=ApiGroup.POST_MUTATION)
@Log(title='岗位管理', business_type=BusinessType.DELETE)
async def delete_system_post(
    request: Request,
    post_ids: Annotated[str, Path(description='需要删除的岗位ID')],
) -> Response:
    delete_post = DeletePostModel(postIds=post_ids)
    delete_post_result = await PostService.delete_post_services(delete_post)
    logger.info(delete_post_result.message)

    return ResponseUtil.success(msg=delete_post_result.message)


@post_controller.get(
    '/{post_id}',
    summary='获取岗位详情接口',
    description='用于获取指定岗位的详细信息',
    response_model=DataResponseModel[PostModel],
    dependencies=[UserInterfaceAuthDependency('system:post:query')],
)
@ApiCache(namespace=ApiNamespace.SYSTEM_POST_DETAIL)
async def query_detail_system_post(
    request: Request,
    post_id: Annotated[int, Path(description='岗位ID')],
) -> Response:
    post_detail_result = await PostService.post_detail_services(post_id)
    logger.info(f'获取post_id为{post_id}的信息成功')

    return ResponseUtil.success(data=post_detail_result)


@post_controller.post(
    '/export',
    summary='导出岗位列表接口',
    description='用于导出当前符合查询条件的岗位列表数据',
    response_class=StreamingResponse,
    responses={
        200: {
            'description': '流式返回岗位列表excel文件',
            'content': {
                'application/octet-stream': {},
            },
        }
    },
    dependencies=[UserInterfaceAuthDependency('system:post:export')],
)
@ApiRateLimit(namespace=ApiNamespace.SYSTEM_POST_EXPORT, preset=ApiRateLimitPreset.USER_RESOURCE_EXPORT)
@Log(title='岗位管理', business_type=BusinessType.EXPORT)
async def export_system_post_list(
    request: Request,
    post_page_query: Annotated[PostPageQueryModel, Form()],
) -> Response:
    # 获取全量数据
    post_query_result = await PostService.get_post_list_services(post_page_query, is_page=False)
    post_export_result = await PostService.export_post_list_services(post_query_result)
    logger.info('导出成功')

    return ResponseUtil.streaming(data=bytes2file_response(post_export_result))
