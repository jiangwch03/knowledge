from typing import Any

from sqlalchemy import select, update

from knowledge_common.common.transactional import get_current_session
from knowledge_common.enums.del_flag_enum import DeleteFlag
from knowledge_common.common.vo import PageModel
from knowledge_common.mapper.do.ai_model_function_adapter_do import AiModelFunctionAdapter
from knowledge_common.mapper.do.ai_models_do import AiModels
from knowledge_common.mapper.dao.base_dao import BaseDao
from knowledge_common.utils.page_util import PageUtil
from knowledge_common.vo.ai_model_function_adapter_vo import (
    AiModelConfigModel,
    AiModelFunctionAdapterModel,
    AiModelFunctionAdapterPageQueryModel,
)


class AiModelFunctionAdapterDao(BaseDao):
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
        根据参数ID获取模型配置（返回第一个可用模型）

        model_id 字段以管道符（|）分隔存储多个模型ID，此方法取第一个
        状态为启用的模型返回。

        :param param_id: 参数ID
        :return: 模型配置 VO（含业务元数据 + 技术参数），未配置时返回 None
        """
        adapters = await cls.get_adapters_by_param_id(param_id)
        return adapters[0] if adapters else None

    @classmethod
    async def get_adapters_by_param_id(cls, param_id: str) -> list[AiModelConfigModel]:
        """
        根据参数ID获取所有配置的模型（支持多模型）

        model_id 字段以管道符（|）分隔存储多个模型ID，此方法返回所有
        状态为启用的模型配置列表。

        :param param_id: 参数ID
        :return: 模型配置 VO 列表，未配置时返回空列表
        """
        db = get_current_session()
        adapter = (
            (await db.execute(
                select(AiModelFunctionAdapter).where(
                    AiModelFunctionAdapter.param_id == param_id,
                    AiModelFunctionAdapter.del_flag == DeleteFlag.NORMAL.value,
                )
            ))
            .scalars()
            .first()
        )
        if not adapter or not adapter.model_id:
            return []

        model_ids = [int(x) for x in str(adapter.model_id).split('|') if x.strip()]
        if not model_ids:
            return []

        rows = (
            (await db.execute(
                select(
                    AiModels.model_id,
                    AiModels.model_code,
                    AiModels.model_name,
                    AiModels.provider,
                    AiModels.api_key,
                    AiModels.base_url,
                    AiModels.model_type,
                    AiModels.max_tokens,
                    AiModels.temperature,
                    AiModels.support_reasoning,
                    AiModels.support_images,
                    AiModels.support_text_inputs,
                    AiModels.support_audio_inputs,
                    AiModels.support_video_inputs,
                    AiModels.support_text_outputs,
                    AiModels.support_image_outputs,
                    AiModels.support_audio_outputs,
                    AiModels.support_video_outputs,
                    AiModels.support_tool_call,
                    AiModels.support_tool_choice,
                    AiModels.support_structured_output,
                    AiModels.support_image_url_inputs,
                    AiModels.support_pdf_inputs,
                    AiModels.support_pdf_tool_message,
                    AiModels.support_image_tool_message,
                    AiModels.max_input_tokens,
                ).where(
                    AiModels.model_id.in_(model_ids),
                    AiModels.status == '0',
                )
            ))
            .mappings()
            .all()
        )
        return [
            AiModelConfigModel(
                adapter_id=adapter.adapter_id,
                function_point=adapter.function_point,
                param_id=adapter.param_id,
                dimensions=adapter.dimensions,
                **row,
            )
            for row in rows
        ]

    @classmethod
    async def get_adapter_list(
        cls, query_object: AiModelFunctionAdapterPageQueryModel, is_page: bool = False
    ) -> PageModel | list:
        """
        分页查询模型功能适配列表

        model_id 字段以管道符（|）分隔存储多个模型ID，列表仅展示第一个
        启用模型的 code 和 name。

        :param query_object: 查询参数对象
        :param is_page: 是否开启分页
        :return: 适配列表分页结果
        """
        db = get_current_session()
        query = (
            select(AiModelFunctionAdapter)
            .where(
                AiModelFunctionAdapter.del_flag == DeleteFlag.NORMAL.value,
                AiModelFunctionAdapter.function_point.like(f'%{query_object.function_point}%')
                if query_object.function_point
                else True,
                AiModelFunctionAdapter.param_id == query_object.param_id if query_object.param_id else True,
            )
            .order_by(AiModelFunctionAdapter.create_time.desc())
        )
        result = await PageUtil.paginate(query, query_object.page_num, query_object.page_size, is_page)

        # 两步查询：批量收集首个有效 model_id，查询对应模型信息
        # PageUtil.paginate 已将行转为小驼峰 dict（modelId），需兼容 ORM / snake / camel
        adapters: list = result.rows if isinstance(result, PageModel) else result
        primary_model_ids: list[int] = []
        for adapter in adapters:
            raw = cls._extract_model_id_raw(adapter)
            first_id = str(raw).split('|')[0].strip() if raw else ''
            if first_id.isdigit() and int(first_id) not in primary_model_ids:
                primary_model_ids.append(int(first_id))

        model_map: dict[int, dict] = {}
        if primary_model_ids:
            rows = (
                (await db.execute(
                    select(
                        AiModels.model_id,
                        AiModels.model_code,
                        AiModels.model_name,
                        AiModels.model_type,
                    ).where(AiModels.model_id.in_(primary_model_ids))
                ))
                .mappings()
                .all()
            )
            model_map = {r['model_id']: dict(r) for r in rows}

        # 拼装结果：adapter + modelCode/modelName/modelType（与 PageUtil 驼峰输出一致）
        enriched: list[dict] = []
        for adapter in adapters:
            if isinstance(adapter, dict):
                row = dict(adapter)
            elif hasattr(adapter, '__table__'):
                row = {c.name: getattr(adapter, c.name) for c in adapter.__table__.columns}
            else:
                row = dict(adapter)
            raw = cls._extract_model_id_raw(row)
            first_token = str(raw).split('|')[0].strip() if raw else ''
            first_id = int(first_token) if first_token.isdigit() else None
            m = model_map.get(first_id) if first_id else None
            model_code = m['model_code'] if m else None
            model_name = m['model_name'] if m else None
            model_type = m['model_type'] if m else None
            row['modelCode'] = model_code
            row['modelName'] = model_name
            row['modelType'] = model_type
            row['model_code'] = model_code
            row['model_name'] = model_name
            row['model_type'] = model_type
            enriched.append(row)

        if isinstance(result, PageModel):
            result.rows = enriched
        else:
            result = enriched
        return result

    @staticmethod
    def _extract_model_id_raw(adapter: object) -> str:
        """从 ORM / dict（snake 或 camel）取出 model_id 原始字符串。"""
        if isinstance(adapter, dict):
            raw = adapter.get('model_id', adapter.get('modelId', ''))
            return '' if raw is None else str(raw)
        raw = getattr(adapter, 'model_id', None)
        return '' if raw is None else str(raw)

    @classmethod
    async def add_adapter_dao(cls, adapter: AiModelFunctionAdapterModel) -> AiModelFunctionAdapter:
        """
        新增模型功能适配记录

        :param adapter: 适配对象
        :return: 适配记录对象
        """
        db = get_current_session()
        db_model = AiModelFunctionAdapter(
            **adapter.model_dump(
                exclude_unset=True,
                exclude={'model_code', 'model_name', 'model_type'},
            )
        )
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
