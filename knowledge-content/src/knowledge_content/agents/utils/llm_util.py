"""
LLM 实例工厂辅助模块

提供爬虫 Agent 的模型配置加载与 BaseChatModel 获取能力。
"""

from langchain_core.language_models.chat_models import BaseChatModel

from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.config.env import AiModelFunctionAdapterConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.langchain_model_vo import ChatModelConfigModel


async def get_base_chat_model(model_id: int | None = None) -> BaseChatModel:
    """
    获取裸 ChatModel（不绑定 tools / retry）

    供 create_agent + wrap_model_call middleware 按 runtime context.model_id 动态换模型。
    """
    model_config = await _get_model_config(model_id)
    return LangChainModelFactory.get_base_chat_model(model_config)


def _to_chat_model_config(adapter: AiModelConfigModel) -> ChatModelConfigModel:
    if not adapter.model_code:
        raise ServiceException('模型配置缺少 model_code，异常终止')
    if not adapter.provider:
        raise ServiceException('模型配置缺少 provider，异常终止')

    return ChatModelConfigModel(
        model_code=adapter.model_code,
        provider=adapter.provider,
        api_key=adapter.api_key or '',
        base_url=adapter.base_url or '',
        temperature=adapter.temperature if adapter.temperature is not None else 0.7,
        max_tokens=adapter.max_tokens,
    )

async def _load_crawler_adapters() -> list[AiModelConfigModel]:
    """
    加载爬虫 Agent 可用模型适配列表（每次直接回源 DB）。
    """
    param_id = AiModelFunctionAdapterConfig.crawler_agent_param_id
    adapters = await AiModelFunctionAdapterDao.get_adapters_by_param_id(param_id)
    if not adapters:
        raise ServiceException(message=f'未配置 {param_id} 模型功能适配')
    return adapters


async def _get_model_config(model_id: int | None = None) -> ChatModelConfigModel:
    """
    从数据库获取爬虫 Agent 可用的 ChatModel 配置

    model_id 对应 ai_models.model_id（前端 get_crawler_models 返回值）。
    为 None 或不在可用列表时，回退到功能点下第一个启用模型。

    :param model_id: 用户选择的模型 ID
    :return: ChatModel 工厂入参
    """
    adapters = await _load_crawler_adapters()

    if model_id is not None:
        matched = next((adapter for adapter in adapters if adapter.model_id == model_id), None)
        if matched is not None:
            return _to_chat_model_config(matched)
        logger.warning(
            '[LLM] model_id={} 不在爬虫 Agent 可用列表，回退默认模型 model_id={}',
            model_id,
            adapters[0].model_id,
        )

    return _to_chat_model_config(adapters[0])
