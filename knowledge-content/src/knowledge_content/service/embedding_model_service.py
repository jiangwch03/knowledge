"""document_embedding 业务封装：委托 common，并映射 content 侧 VO。"""

from knowledge_common.service.document_embedding_service import DocumentEmbeddingService
from knowledge_content.vo.embedding_vo import EmbeddingModelInfoVo


class EmbeddingModelService:
    """document_embedding 模型信息（content 管理端）。"""

    @classmethod
    async def get_model_info(cls) -> EmbeddingModelInfoVo:
        adapter = await DocumentEmbeddingService.load_adapter()
        return EmbeddingModelInfoVo(
            model_code=adapter.model_code,
            dimensions=adapter.dimensions,
            provider=adapter.provider,
        )

    @classmethod
    async def get_dimensions(cls) -> int:
        return await DocumentEmbeddingService.get_dimensions()
