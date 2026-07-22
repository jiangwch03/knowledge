from datetime import datetime
from typing import Any

from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.mapper.dao.ai_models_dao import AiModelDao
from knowledge_common.mapper.do.ai_model_function_adapter_do import AiModelFunctionAdapter
from knowledge_common.mapper.do.ai_models_do import AiModels
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

    _DOCUMENT_EMBEDDING_PARAM = 'document_embedding'
    _EMBEDDING_MODEL_TYPE = 'embedding'

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
        result: PageModel | list = await AiModelFunctionAdapterDao.get_adapter_list(query_object, is_page)
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
        config: AiModelConfigModel | None = await AiModelFunctionAdapterDao.get_adapter_by_param_id(param_id)
        if not config:
            raise ServiceException(f'参数ID [{param_id}] 未配置模型适配')
        return AiModelConfigModel(**CamelCaseUtil.transform_result(config))

    @classmethod
    async def get_adapter_configs_by_param_id_services(cls, param_id: str) -> list[AiModelConfigModel]:
        """
        根据参数ID获取所有配置的模型列表

        :param param_id: 参数ID
        :return: 模型配置列表（含业务元数据 + 技术参数）
        """
        configs: list[AiModelConfigModel] = await AiModelFunctionAdapterDao.get_adapters_by_param_id(param_id)
        if not configs:
            raise ServiceException(f'参数ID [{param_id}] 未配置模型适配')
        return [AiModelConfigModel(**CamelCaseUtil.transform_result(c)) for c in configs]

    @classmethod
    async def _validate_models(
        cls,
        model_id_str: str,
        *,
        param_id: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        """
        校验所有模型是否存在且启用。

        绑定 Embedding 模型时须配置有效维度；
        param_id=document_embedding 时绑定的模型必须为 embedding。
        """
        ids: list[str] = [x.strip() for x in model_id_str.split('|') if x.strip()]
        if not ids:
            raise ServiceException('模型ID不能为空')
        require_embedding: bool = (param_id or '').strip() == cls._DOCUMENT_EMBEDDING_PARAM
        has_embedding: bool = False
        for mid in ids:
            if not mid.isdigit():
                raise ServiceException(f'模型ID格式不合法: {mid}')
            model: AiModels | None = await AiModelDao.get_ai_model_detail_by_id(int(mid))
            if not model:
                raise ServiceException(f'模型ID [{mid}] 不存在')
            if model.status != '0':
                raise ServiceException(f'模型ID [{mid}] 已停用')
            model_type: str = (model.model_type or '').strip().lower()
            is_embedding: bool = model_type == cls._EMBEDDING_MODEL_TYPE
            if is_embedding:
                has_embedding = True
            if require_embedding and not is_embedding:
                raise ServiceException(
                    f'参数 document_embedding 须绑定 Embedding 模型，模型 [{model.model_code}] 类型为 [{model.model_type}]'
                )
        if has_embedding and (dimensions is None or dimensions <= 0):
            raise ServiceException('绑定 Embedding 模型时须配置大于 0 的向量维度')

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
        await cls._validate_models(
            page_object.model_id,
            param_id=page_object.param_id,
            dimensions=page_object.dimensions,
        )

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
        adapter: AiModelFunctionAdapter | None = await AiModelFunctionAdapterDao.get_adapter_by_id(
            page_object.adapter_id
        )
        if not adapter:
            raise ServiceException('适配记录不存在')

        if await AiModelFunctionAdapterDao.check_param_id_exists(
            page_object.param_id, exclude_adapter_id=page_object.adapter_id
        ):
            raise ServiceException(f'参数ID [{page_object.param_id}] 重复定义')
        await cls._validate_models(
            page_object.model_id,
            param_id=page_object.param_id,
            dimensions=page_object.dimensions,
        )

        edit_adapter: dict[str, Any] = page_object.model_dump(
            exclude_unset=True,
            exclude={'model_code', 'model_name', 'model_type'},
        )
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
        adapter: AiModelFunctionAdapter | None = await AiModelFunctionAdapterDao.get_adapter_by_id(adapter_id)
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
