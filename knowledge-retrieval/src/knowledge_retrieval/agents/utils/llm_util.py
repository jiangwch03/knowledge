"""知识问答 Agent 模型加载。"""

from langchain_core.language_models.chat_models import BaseChatModel

from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.config.env import AiModelFunctionAdapterConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.langchain_model_vo import ChatModelConfigModel


async def get_base_chat_model(model_id: int | None = None) -> BaseChatModel:
    model_config = await _get_model_config(model_id)
    return LangChainModelFactory.get_base_chat_model(model_config)


def _to_chat_model_config(adapter: AiModelConfigModel) -> ChatModelConfigModel:
    if not adapter.model_code or not adapter.provider:
        raise ServiceException('模型配置缺少 model_code/provider')
    return ChatModelConfigModel(
        model_code=adapter.model_code,
        provider=adapter.provider,
        api_key=adapter.api_key or '',
        base_url=adapter.base_url or '',
        temperature=adapter.temperature if adapter.temperature is not None else 0.3,
        max_tokens=adapter.max_tokens,
    )


async def _load_adapters() -> list[AiModelConfigModel]:
    param_id = AiModelFunctionAdapterConfig.knowledge_qa_agent_param_id
    adapters = await AiModelFunctionAdapterDao.get_adapters_by_param_id(param_id)
    if not adapters:
        adapters = await AiModelFunctionAdapterDao.get_adapters_by_param_id(
            AiModelFunctionAdapterConfig.crawler_agent_param_id
        )
    if not adapters:
        raise ServiceException(message=f'未配置 {param_id} 模型功能适配')
    return adapters


async def _get_model_config(model_id: int | None = None) -> ChatModelConfigModel:
    adapters = await _load_adapters()
    if model_id is not None:
        matched = next((adapter for adapter in adapters if adapter.model_id == model_id), None)
        if matched is not None:
            return _to_chat_model_config(matched)
        logger.warning('[KnowledgeQA] model_id={} 不可用，回退默认', model_id)
    return _to_chat_model_config(adapters[0])
