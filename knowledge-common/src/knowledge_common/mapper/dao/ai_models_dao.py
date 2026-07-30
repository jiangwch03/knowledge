from typing import Any

from sqlalchemy import ColumnElement, delete, select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.do.ai_models_do import AiModels
from knowledge_common.utils.page_util import PageUtil
from knowledge_common.vo.ai_model_vo import AiModelModel, AiModelPageQueryModel
from knowledge_common.mapper.dao.base_dao import BaseDao


class AiModelDao(BaseDao):
    """
    AI模型管理数据库操作层
    """

    @classmethod
    async def get_ai_model_detail_by_id(cls, model_id: int) -> AiModels | None:
        """
        根据AI模型id获取AI模型详细信息

        :param model_id: AI模型id
        :return: AI模型信息对象
        """
        db = get_current_session()
        ai_model_info = (await db.execute(select(AiModels).where(AiModels.model_id == model_id))).scalars().first()

        return ai_model_info

    @classmethod
    async def get_ai_model_by_code(cls, model_code: str) -> AiModels | None:
        """
        根据模型编码获取AI模型

        :param model_code: 模型编码
        :return: AI模型信息对象
        """
        db = get_current_session()
        return (
            (await db.execute(select(AiModels).where(AiModels.model_code == model_code, AiModels.del_flag == DeleteFlag.NORMAL.value)))
            .scalars()
            .first()
        )

    @classmethod
    async def get_ai_model_list(
        cls, query_object: AiModelPageQueryModel, data_scope_sql: ColumnElement, is_page: bool = False
    ) -> PageModel | list:
        """
        根据查询参数获取AI模型列表信息

        :param query_object: 查询参数对象
        :param data_scope_sql: 数据权限对应的查询sql语句
        :param is_page: 是否开启分页
        :return: AI模型列表信息对象
        """
        query = (
            select(AiModels)
            .where(
                AiModels.model_id == query_object.model_id if query_object.model_id else True,
                AiModels.model_name.like(f'%{query_object.model_name}%') if query_object.model_name else True,
                AiModels.model_code.like(f'%{query_object.model_code}%') if query_object.model_code else True,
                AiModels.provider == query_object.provider if query_object.provider else True,
                AiModels.status == query_object.status if query_object.status else True,
                data_scope_sql,
            )
            .order_by(AiModels.model_sort)
        )
        ai_model_list = await PageUtil.paginate(
            query, query_object.page_num, query_object.page_size, is_page
        )

        return ai_model_list

    @classmethod
    async def add_ai_model_dao(cls, ai_model: AiModelModel) -> AiModels:
        """
        新增AI模型数据库操作

        :param ai_model: AI模型对象
        :return: AI模型信息对象
        """
        db = get_current_session()
        db_model = AiModels(**ai_model.model_dump(exclude_unset=True))
        db.add(db_model)
        await db.flush()

        return db_model

    @classmethod
    async def edit_ai_model_dao(cls, ai_model: dict[str, Any]) -> None:
        """
        编辑AI模型数据库操作

        :param ai_model: 需要更新的AI模型字典
        :return:
        """
        db = get_current_session()
        await db.execute(update(AiModels), [ai_model])

    @classmethod
    async def delete_ai_model_dao(cls, ai_model: AiModelModel) -> None:
        """
        删除AI模型数据库操作

        :param ai_model: AI模型对象
        :return:
        """
        db = get_current_session()
        await db.execute(delete(AiModels).where(AiModels.model_id.in_([ai_model.model_id])))
