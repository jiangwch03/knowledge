from datetime import datetime
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.mapper.dao.ai_models_dao import AiModelDao
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.vo.ai_model_function_adapter_vo import (
    AiModelConfigModel,
    AiModelFunctionAdapterModel,
    AiModelFunctionAdapterPageQueryModel,
)


class AiModelFunctionAdapterService:
    """
    模型功能适配服务层
    """

    @classmethod
    async def get_adapter_list_services(
        cls,
        query_object: AiModelFunctionAdapterPageQueryModel,
        is_page: bool = True,
    ) -> PageModel[AiModelFunctionAdapterModel] | list[AiModelFunctionAdapterModel]:
        """
        获取模型功能适配列表

        :param query_object: 查询对象
        :param is_page: 是否分页
        :return: 适配列表
        """
        result = await AiModelFunctionAdapterDao.get_adapter_list(query_object, is_page)
        if isinstance(result, PageModel):
            result.rows = [AiModelFunctionAdapterModel(**row) for row in result.rows]
            return result
        return [AiModelFunctionAdapterModel(**row) for row in result]

    @classmethod
    async def get_adapter_config_by_param_id_services(cls, param_id: str) -> AiModelConfigModel:
        """
        根据参数ID获取模型配置

        :param param_id: 参数ID
        :return: 模型配置（含业务元数据 + 技术参数）
        """
        config = await AiModelFunctionAdapterDao.get_adapter_by_param_id(param_id)
        if not config:
            raise ServiceException(f'参数ID [{param_id}] 未配置模型适配')
        return AiModelConfigModel(**CamelCaseUtil.transform_result(config))

    @classmethod
    async def _validate_model(cls, model_id: int) -> None:
        """校验模型是否存在且启用"""
        model = await AiModelDao.get_ai_model_detail_by_id(model_id)
        if not model:
            raise ServiceException('模型不存在')
        if model.status != '0':
            raise ServiceException('模型已停用')

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def add_adapter_services(
        cls,
        page_object: AiModelFunctionAdapterModel,
        user_name: str,
    ) -> CrudResponseModel:
        """
        新增模型功能适配

        :param page_object: 适配对象
        :param user_name: 用户名
        :return: 操作结果
        """
        if await AiModelFunctionAdapterDao.check_param_id_exists(page_object.param_id):
            raise ServiceException(f'参数ID [{page_object.param_id}] 重复定义')
        await cls._validate_model(page_object.model_id)

        page_object.create_by = user_name
        page_object.update_by = user_name
        page_object.create_time = datetime.now()
        page_object.update_time = datetime.now()
        await AiModelFunctionAdapterDao.add_adapter_dao(page_object)
        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def edit_adapter_services(
        cls,
        page_object: AiModelFunctionAdapterModel,
        user_name: str,
    ) -> CrudResponseModel:
        """
        修改模型功能适配

        :param page_object: 适配对象
        :param user_name: 用户名
        :return: 操作结果
        """
        adapter = await AiModelFunctionAdapterDao.get_adapter_by_id(page_object.adapter_id)
        if not adapter:
            raise ServiceException('适配记录不存在')

        if await AiModelFunctionAdapterDao.check_param_id_exists(
            page_object.param_id, exclude_adapter_id=page_object.adapter_id
        ):
            raise ServiceException(f'参数ID [{page_object.param_id}] 重复定义')
        await cls._validate_model(page_object.model_id)

        edit_adapter = page_object.model_dump(exclude_unset=True)
        edit_adapter['update_by'] = user_name
        edit_adapter['update_time'] = datetime.now()
        await AiModelFunctionAdapterDao.edit_adapter_dao(edit_adapter)
        return CrudResponseModel(is_success=True, message='修改成功')

    @classmethod
    @transactional(rollback_for=(Exception,))
    async def delete_adapter_services(cls, adapter_id: int, user_name: str) -> CrudResponseModel:
        """
        删除模型功能适配

        :param adapter_id: 适配ID
        :param user_name: 用户名
        :return: 操作结果
        """
        adapter = await AiModelFunctionAdapterDao.get_adapter_by_id(adapter_id)
        if not adapter:
            raise ServiceException('适配记录不存在')

        await AiModelFunctionAdapterDao.edit_adapter_dao(
            {
                'adapter_id': adapter_id,
                'del_flag': DeleteFlag.DELETED.value,
                'update_by': user_name,
                'update_time': datetime.now(),
            }
        )
        return CrudResponseModel(is_success=True, message='删除成功')
