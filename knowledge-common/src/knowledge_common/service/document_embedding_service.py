"""document_embedding：适配加载 + 文本向量化（入库 / 检索共用）。

对外只暴露「文本 → 向量」；底层模型客户端为内部实现细节。
"""

from __future__ import annotations

from langchain_core.embeddings import Embeddings

from knowledge_common.common import with_session
from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.config.env import AiModelFunctionAdapterConfig, EmbeddingConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.langchain_model_vo import EmbeddingModelConfigModel


class DocumentEmbeddingService:
    """document_embedding 适配与向量生成。"""

    @classmethod
    @with_session
    async def load_adapter(cls) -> AiModelConfigModel:
        adapters = await AiModelFunctionAdapterDao.get_adapters_by_param_id(
            AiModelFunctionAdapterConfig.document_embedding_param_id
        )
        if not adapters:
            raise ServiceException('未配置 document_embedding 模型适配，请联系管理员')
        adapter = adapters[0]
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
    async def _client(cls) -> Embeddings:
        adapter = await cls.load_adapter()
        return LangChainModelFactory.create_embedding_model(cls._to_config(adapter))

    @classmethod
    async def get_dimensions(cls) -> int:
        adapter = await cls.load_adapter()
        return adapter.dimensions

    @classmethod
    async def embed_query(cls, query: str) -> list[float]:
        """单条文本 → 向量（检索 query 侧）。"""
        return list(await (await cls._client()).aembed_query(query))

    @classmethod
    async def embed_documents(cls, texts: list[str]) -> list[list[float]]:
        """批量文本 → 向量（入库向量化阶段）。"""
        if not texts:
            return []
        vectors = await (await cls._client()).aembed_documents(texts)
        return [list(v) for v in vectors]
