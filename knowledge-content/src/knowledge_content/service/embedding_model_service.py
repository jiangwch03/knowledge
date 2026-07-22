from langchain_core.embeddings import Embeddings

from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.config.env import AiModelFunctionAdapterConfig, EmbeddingConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.langchain_model_vo import EmbeddingModelConfigModel

from knowledge_content.vo.embedding_vo import EmbeddingModelInfoVo


class EmbeddingModelService:
    """document_embedding 适配读取与 LangChain Embeddings 创建"""

    @classmethod
    async def _load_adapter(cls) -> AiModelConfigModel:
        adapters: list[AiModelConfigModel] = await AiModelFunctionAdapterDao.get_adapters_by_param_id(
            AiModelFunctionAdapterConfig.document_embedding_param_id
        )
        if not adapters:
            raise ServiceException('未配置 document_embedding 模型适配，请联系管理员')
        adapter: AiModelConfigModel = adapters[0]
        if not adapter.dimensions or adapter.dimensions <= 0:
            raise ServiceException('document_embedding 适配未配置有效向量维度')
        if not adapter.model_code or not adapter.provider:
            raise ServiceException('document_embedding 适配模型信息不完整')
        return adapter

    @classmethod
    def _to_config(cls, adapter: AiModelConfigModel) -> EmbeddingModelConfigModel:
        return EmbeddingModelConfigModel(
            model_code=adapter.model_code,
            provider=adapter.provider,
            api_key=adapter.api_key or '',
            base_url=adapter.base_url or '',
            dimensions=adapter.dimensions,
            chunk_size=EmbeddingConfig.embedding_api_chunk_size,
            check_embedding_ctx_length=EmbeddingConfig.embedding_check_ctx_length,
        )

    @classmethod
    async def get_model_info(cls) -> EmbeddingModelInfoVo:
        adapter: AiModelConfigModel = await cls._load_adapter()
        return EmbeddingModelInfoVo(
            model_code=adapter.model_code,
            dimensions=adapter.dimensions,
            provider=adapter.provider,
        )

    @classmethod
    async def create_embeddings(cls) -> Embeddings:
        adapter: AiModelConfigModel = await cls._load_adapter()
        return LangChainModelFactory.create_embedding_model(cls._to_config(adapter))

    @classmethod
    async def get_dimensions(cls) -> int:
        adapter: AiModelConfigModel = await cls._load_adapter()
        return adapter.dimensions
