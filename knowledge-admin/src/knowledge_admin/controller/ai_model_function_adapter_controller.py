from datetime import datetime
from typing import Annotated

from fastapi import Path, Query, Request, Response
from knowledge_common.common.annotation.cache_annotation import ApiCache, ApiCacheEvict
from knowledge_common.common.annotation.log_annotation import Log
from knowledge_common.common.aspect.interface_auth import UserInterfaceAuthDependency
from knowledge_common.common.aspect.pre_auth import CurrentUserDependency, PreAuthDependency
from knowledge_common.common.constant import ApiGroup, ApiNamespace
from knowledge_common.common.enums import BusinessType
from knowledge_common.common.router import APIRouterPro
from knowledge_common.common.vo import DataResponseModel, PageResponseModel, ResponseBaseModel
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.response_util import ResponseUtil
from knowledge_common.vo.ai_model_function_adapter_vo import (
    AiModelConfigModel,
    AiModelFunctionAdapterModel,
    AiModelFunctionAdapterPageQueryModel,
)
from knowledge_common.vo.user_vo import CurrentUserModel
from pydantic_validation_decorator import ValidateFields

from knowledge_admin.service.ai_model_function_adapter_service import AiModelFunctionAdapterService

ai_model_function_adapter_controller = APIRouterPro(
    prefix='/ai/model/function-adapter', order_num=19, tags=['AI管理-模型功能适配'], dependencies=[PreAuthDependency()]
)


@ai_model_function_adapter_controller.get(
    '/list',
    summary='获取模型功能适配分页列表',
    description='用于获取模型功能适配分页列表',
    response_model=PageResponseModel[AiModelFunctionAdapterModel],
    dependencies=[UserInterfaceAuthDependency('ai:model:function-adapter:list')],
)
@ApiCache(namespace=ApiNamespace.AI_MODEL_FUNCTION_ADAPTER_LIST)
async def get_adapter_list(
    request: Request,
    query_object: Annotated[AiModelFunctionAdapterPageQueryModel, Query()],
) -> Response:
    result = await AiModelFunctionAdapterService.get_adapter_list_services(query_object, is_page=True)
    logger.info('获取模型功能适配列表成功')
    return ResponseUtil.success(model_content=result)


@ai_model_function_adapter_controller.get(
    '/{param_id}/model',
    summary='根据参数ID获取模型配置',
    description='用于业务模块按参数ID读取模型配置',
    response_model=DataResponseModel[AiModelConfigModel],
)
async def get_adapter_config_by_param_id(
    request: Request,
    param_id: Annotated[str, Path(description='参数ID')],
) -> Response:
    result = await AiModelFunctionAdapterService.get_adapter_config_by_param_id_services(param_id)
    logger.info(f'获取参数ID [{param_id}] 模型配置成功')
    return ResponseUtil.success(data=result)


@ai_model_function_adapter_controller.post(
    '',
    summary='新增模型功能适配',
    description='用于新增模型功能适配',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('ai:model:function-adapter:add')],
)
@ValidateFields(validate_model='add_adapter')
@ApiCacheEvict(namespaces=ApiGroup.AI_MODEL_FUNCTION_ADAPTER_MUTATION)
@Log(title='模型功能适配', business_type=BusinessType.INSERT)
async def add_adapter(
    request: Request,
    add_adapter_model: AiModelFunctionAdapterModel,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await AiModelFunctionAdapterService.add_adapter_services(
        add_adapter_model, current_user.user.user_name
    )
    logger.info(result.message)
    return ResponseUtil.success(msg=result.message)


@ai_model_function_adapter_controller.put(
    '/{adapter_id}',
    summary='修改模型功能适配',
    description='用于修改模型功能适配',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('ai:model:function-adapter:edit')],
)
@ValidateFields(validate_model='edit_adapter')
@ApiCacheEvict(namespaces=ApiGroup.AI_MODEL_FUNCTION_ADAPTER_MUTATION)
@Log(title='模型功能适配', business_type=BusinessType.UPDATE)
async def edit_adapter(
    request: Request,
    adapter_id: Annotated[int, Path(description='适配ID')],
    edit_adapter_model: AiModelFunctionAdapterModel,
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    edit_adapter_model.adapter_id = adapter_id
    edit_adapter_model.update_by = current_user.user.user_name
    edit_adapter_model.update_time = datetime.now()
    result = await AiModelFunctionAdapterService.edit_adapter_services(
        edit_adapter_model, current_user.user.user_name
    )
    logger.info(result.message)
    return ResponseUtil.success(msg=result.message)


@ai_model_function_adapter_controller.delete(
    '/{adapter_id}',
    summary='删除模型功能适配',
    description='用于删除模型功能适配',
    response_model=ResponseBaseModel,
    dependencies=[UserInterfaceAuthDependency('ai:model:function-adapter:remove')],
)
@ApiCacheEvict(namespaces=ApiGroup.AI_MODEL_FUNCTION_ADAPTER_MUTATION)
@Log(title='模型功能适配', business_type=BusinessType.DELETE)
async def delete_adapter(
    request: Request,
    adapter_id: Annotated[int, Path(description='适配ID')],
    current_user: Annotated[CurrentUserModel, CurrentUserDependency()],
) -> Response:
    result = await AiModelFunctionAdapterService.delete_adapter_services(
        adapter_id, current_user.user.user_name
    )
    logger.info(result.message)
    return ResponseUtil.success(msg=result.message)
