from typing import Any

from knowledge_admin.service.models_dev_profile_service import ModelsDevProfileService
from knowledge_common.common.transactional import transactional
from knowledge_common.common.vo import CrudResponseModel, PageModel
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_models_dao import AiModelDao
from knowledge_common.utils.common_util import CamelCaseUtil
from knowledge_common.utils.crypto_util import CryptoUtil
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.ai_model_vo import AiModelModel, AiModelPageQueryModel, DeleteAiModelModel
from knowledge_common.vo.model_profile_vo import ModelProfileVo
from sqlalchemy import ColumnElement


class AiModelService:
    """
    AI模型管理服务层
    """

    @classmethod
    async def get_ai_model_list_services(
        cls,
        query_object: AiModelPageQueryModel,
        data_scope_sql: ColumnElement,
        is_page: bool = False,
    ) -> PageModel | list[dict[str, Any]]:
        """
        获取AI模型列表信息service

        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: AI模型列表信息对象
        """
        ai_model_list_result = await AiModelDao.get_ai_model_list(query_object, data_scope_sql, is_page)
        rows = ai_model_list_result.rows if isinstance(ai_model_list_result, PageModel) else ai_model_list_result

        for row in rows:
            if 'apiKey' in row:
                row['apiKey'] = '********' * 3

        return ai_model_list_result

    @classmethod
    async def check_ai_model_data_scope_services(
        cls,
        model_id: int,
        data_scope_sql: ColumnElement,
    ) -> CrudResponseModel:
        """
        校验用户是否有AI模型数据权限service

        :param model_id: 模型主键
        :param data_scope_sql: 数据权限对应的查询sql语句
        :return: 校验结果
        """
        ai_models = await AiModelDao.get_ai_model_list(
            AiModelModel(modelId=model_id), data_scope_sql, is_page=False
        )
        if ai_models:
            return CrudResponseModel(is_success=True, message='校验通过')
        raise ServiceException(message='没有权限访问AI模型数据')

    @classmethod
    @transactional()
    async def add_ai_model_services(cls, page_object: AiModelModel) -> CrudResponseModel:
        """
        新增AI模型信息service

        :param request: Request对象
        :param page_object: 新增AI模型对象
        :return: 新增AI模型校验结果
        """
        if page_object.api_key:
            page_object.api_key = CryptoUtil.encrypt(page_object.api_key)
        await AiModelDao.add_ai_model_dao(page_object)
        return CrudResponseModel(is_success=True, message='新增成功')

    @classmethod
    @transactional()
    async def edit_ai_model_services(cls, page_object: AiModelModel) -> CrudResponseModel:
        """
        编辑AI模型信息service

        :param page_object: 编辑AI模型对象
        :return: 编辑AI模型校验结果
        """
        edit_ai_model = page_object.model_dump(exclude_unset=True)
        if page_object.api_key:
            if page_object.api_key == '********' * 3:
                if 'api_key' in edit_ai_model:
                    del edit_ai_model['api_key']
            else:
                edit_ai_model['api_key'] = CryptoUtil.encrypt(page_object.api_key)

        ai_model_info = await cls.ai_model_detail_services(page_object.model_id)
        if ai_model_info.model_id:
            await AiModelDao.edit_ai_model_dao(edit_ai_model)
            return CrudResponseModel(is_success=True, message='修改成功')
        raise ServiceException(message='AI模型不存在')

    @classmethod
    @transactional()
    async def delete_ai_model_services(
        cls, page_object: DeleteAiModelModel
    ) -> CrudResponseModel:
        """
        删除AI模型信息service

        :param page_object: 删除AI模型对象
        :return: 删除AI模型校验结果
        """
        if page_object.model_ids:
            model_id_list = page_object.model_ids.split(',')
            for model_id in model_id_list:
                await AiModelDao.delete_ai_model_dao(AiModelModel(modelId=model_id))
            return CrudResponseModel(is_success=True, message='删除成功')
        raise ServiceException(message='传入AI模型id为空')

    @classmethod
    async def ai_model_detail_services(cls, model_id: int) -> AiModelModel:
        """
        获取AI模型详细信息service

        :param model_id: AI模型id
        :return: AI模型id对应的信息
        """
        ai_model = await AiModelDao.get_ai_model_detail_by_id(model_id=model_id)
        result = AiModelModel(**CamelCaseUtil.transform_result(ai_model)) if ai_model else AiModelModel()

        if result.api_key:
            result.api_key = '********' * 3

        return result

    @classmethod
    async def get_model_profile(
        cls,
        model_code: str,
        provider: str,
        model_type: str | None = None,
    ) -> ModelProfileVo:
        """
        从本地 models.dev 索引获取模型 Profile（按 model_code，不依赖厂商 SDK）

        :param model_code: 模型编码
        :param provider: 提供商（兼容字段；索引按官方源优选，不强制匹配）
        :param model_type: 模型类型，rerank/embedding 直接返回空
        :return: Profile VO
        """
        if model_type in ('rerank', 'embedding'):
            return ModelProfileVo()

        try:
            return await ModelsDevProfileService.get_model_profile(model_code, provider)
        except Exception as e:
            logger.warning(f'获取模型 Profile 失败: {model_code}/{provider} - {e}')
            raise ServiceException(message=f'获取 Profile 失败: {e}')
