"""DashScope 专用工厂：Rerank 等非 Chat/Embeddings 能力。"""

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.vo.langchain_model_vo import RerankModelConfigModel


class DashScopeModelFactory:
    """DashScope 侧能力工厂（当前：TextReRank → DashScopeRerank 压缩器）。"""

    @classmethod
    def create_rerank_compressor(cls, model_config: RerankModelConfigModel):
        """
        根据模型配置创建 LangChain DashScopeRerank 文档压缩器。

        显式传入 dashscope.TextReRank client，避免 community 实现把 model 强制改成 gte-rerank。
        """
        if not (model_config.model_code or '').strip():
            raise ServiceException(message='创建 Rerank 失败: model_code 为空')
        if not (model_config.api_key or '').strip():
            raise ServiceException(message='创建 Rerank 失败: api_key 为空')

        provider = (model_config.provider or '').strip().lower()
        if provider not in {'', 'dashscope', 'alibaba', 'aliyun'}:
            raise ServiceException(message=f'暂不支持的 Rerank provider: {model_config.provider}')

        try:
            import dashscope
            from langchain_community.document_compressors.dashscope_rerank import DashScopeRerank
        except ImportError as e:
            raise ServiceException(message=f'创建 Rerank 失败，请安装 dashscope: {e}') from e

        base = (model_config.base_url or '').strip().rstrip('/')
        if base:
            # SDK 默认国际站；中国区需显式指定
            if base.endswith('/services/rerank/text-rerank/text-rerank'):
                dashscope.base_http_api_url = base[: -len('/services/rerank/text-rerank/text-rerank')] or base
            else:
                dashscope.base_http_api_url = base

        try:
            return DashScopeRerank(
                client=dashscope.TextReRank,
                model=model_config.model_code,
                api_key=model_config.api_key,
                top_n=model_config.top_n if model_config.top_n and model_config.top_n > 0 else None,
            )
        except Exception as e:
            raise ServiceException(message=f'创建 Rerank 压缩器失败: {e}') from e
