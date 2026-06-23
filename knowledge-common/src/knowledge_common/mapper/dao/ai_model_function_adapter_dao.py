from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import aliased

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.do.ai_model_function_adapter_do import AiModelFunctionAdapter
from knowledge_common.mapper.do.ai_models_do import AiModels
from knowledge_common.utils.page_util import PageUtil
from knowledge_common.vo.ai_model_function_adapter_vo import (
    AiModelConfigModel,
    AiModelFunctionAdapterModel,
    AiModelFunctionAdapterPageQueryModel,
)


class AiModelFunctionAdapterDao:
    """
    模型功能适配数据库操作层
    """

    @classmethod
    async def get_adapter_by_id(cls, adapter_id: int) -> AiModelFunctionAdapter | None:
        """
        根据适配ID获取适配记录

        :param adapter_id: 适配ID
        :return: 适配记录对象
        """
        db = get_current_session()
        return (
            (
                await db.execute(
                    select(AiModelFunctionAdapter).where(
                        AiModelFunctionAdapter.adapter_id == adapter_id, AiModelFunctionAdapter.del_flag == DeleteFlag.NORMAL.value # type: ignore
                    )
                )
            )
            .scalars()
            .first()
        )

    @classmethod
    async def get_adapter_by_param_id(cls, param_id: str) -> AiModelConfigModel | None:
        """
        根据参数ID获取模型配置

        :param param_id: 参数ID
        :return: 模型配置 VO（含业务元数据 + 技术参数），未配置时返回 None
        """
        db = get_current_session()
        model_alias = aliased(AiModels)
        result = (
            (
                await db.execute(
                    select(
                        AiModelFunctionAdapter.adapter_id,
                        AiModelFunctionAdapter.function_point,
                        AiModelFunctionAdapter.param_id,
                        model_alias.model_id,
                        model_alias.model_code,
                        model_alias.model_name,
                        model_alias.provider,
                        model_alias.api_key,
                        model_alias.base_url,
                        model_alias.model_type,
                        model_alias.max_tokens,
                        model_alias.temperature,
                        model_alias.support_reasoning,
                        model_alias.support_images,
                    )
                    .select_from(AiModelFunctionAdapter)
                    .join(model_alias, AiModelFunctionAdapter.model_id == model_alias.model_id) # type: ignore
                    .where(
                        AiModelFunctionAdapter.param_id == param_id,
                        AiModelFunctionAdapter.del_flag == DeleteFlag.NORMAL.value,
                        model_alias.status == '0',
                    )
                )
            )
            .mappings()
            .first()
        )
        return AiModelConfigModel(**result) if result else None

    @classmethod
    async def get_adapter_list(
        cls, query_object: AiModelFunctionAdapterPageQueryModel, is_page: bool = False
    ) -> PageModel | list:
        """
        分页查询模型功能适配列表

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 适配列表分页结果
        """
        model_alias = aliased(AiModels)
        query = (
            select(
                AiModelFunctionAdapter,
                model_alias.model_code,
                model_alias.model_name,
            )
            .select_from(AiModelFunctionAdapter)
            .join(model_alias, AiModelFunctionAdapter.model_id == model_alias.model_id) # type: ignore
            .where(
                AiModelFunctionAdapter.del_flag == DeleteFlag.NORMAL.value,
                AiModelFunctionAdapter.function_point.like(f'%{query_object.function_point}%')
                if query_object.function_point
                else True,
                AiModelFunctionAdapter.param_id == query_object.param_id if query_object.param_id else True,
            )
            .order_by(AiModelFunctionAdapter.create_time.desc())
        )
        return await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

    @classmethod
    async def add_adapter_dao(cls, adapter: AiModelFunctionAdapterModel) -> AiModelFunctionAdapter:
        """
        新增模型功能适配记录

        :param adapter: 适配对象
        :return: 适配记录对象
        """
        db = get_current_session()
        db_model = AiModelFunctionAdapter(**adapter.model_dump(exclude_unset=True, exclude={'model_code', 'model_name'}))
        db.add(db_model)
        await db.flush()
        return db_model

    @classmethod
    async def edit_adapter_dao(cls, adapter: dict[str, Any]) -> None:
        """
        编辑模型功能适配记录

        :param adapter: 需要更新的适配字典
        :return:
        """
        db = get_current_session()
        await db.execute(update(AiModelFunctionAdapter), [adapter])

    @classmethod
    async def check_param_id_exists(cls, param_id: str, exclude_adapter_id: int | None = None) -> bool:
        """
        检查参数ID是否已存在

        :param param_id: 参数ID
        :param exclude_adapter_id: 需要排除的适配ID
        :return: 是否存在
        """
        db = get_current_session()
        query = select(AiModelFunctionAdapter).where(
            AiModelFunctionAdapter.param_id == param_id, AiModelFunctionAdapter.del_flag == DeleteFlag.NORMAL.value # type: ignore
        )
        if exclude_adapter_id:
            query = query.where(AiModelFunctionAdapter.adapter_id != exclude_adapter_id)
        result = (await db.execute(query)).scalars().first()
        return result is not None
