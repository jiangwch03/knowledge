"""检索精排：经 DashScopeModelFactory 收口创建 DashScopeRerank。

入参 ``RerankDocumentVo(id, text)``，出参 ``RerankResultVo(id, score)``（按分降序）；
SDK 返回的是下标，这里映射回业务 id 再吐出。
"""

from __future__ import annotations

import asyncio

from knowledge_common.common.factory.dashscope_model_factory import DashScopeModelFactory
from knowledge_common.config.env import AiModelFunctionAdapterConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.mapper.dao.ai_model_function_adapter_dao import AiModelFunctionAdapterDao
from knowledge_common.service.rag_config_service import RagConfigService
from knowledge_common.utils.log_util import logger
from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_common.vo.langchain_model_vo import RerankModelConfigModel
from knowledge_retrieval.vo.rerank_vo import RerankDocumentVo, RerankResultVo


class RerankService:
    """业务侧精排：加载 document_rerank 适配 → 工厂创建压缩器 → 调用 rerank。"""

    @classmethod
    async def rerank(
        cls,
        query: str,
        documents: list[RerankDocumentVo],
        *,
        top_n: int | None = None,
    ) -> list[RerankResultVo] | None:
        """按 query 对候选文档精排；成功返回 ``[{id, score}]``（降序），调用失败返回 None。"""
        if not documents:
            raise ServiceException('精排候选文档不能为空')
        # 加载适配与单文档字符上限（sys_config: rag.rerank.max_doc_chars）
        adapter = await cls._load_adapter()
        max_doc_chars = await RagConfigService.get_rerank_max_doc_chars()

        try:
            # 创建精排模型
            compressor = DashScopeModelFactory.create_rerank_compressor(cls._to_config(adapter, top_n))
            # 截断过长文档正文，避免超出 rerank 模型单条输入上限
            texts = [cls._clip(d.text, max_doc_chars) for d in documents]
            # top_n 未传则全量重排；SDK 同步，丢线程池避免堵事件循环
            limit = top_n if top_n is not None else len(texts)
            # 调用精排模型 起线程 避免堵事件循环
            ranked = await asyncio.to_thread(
                compressor.rerank,
                texts,
                query.strip(),
                top_n=limit,
            )
        except Exception as exc:
            logger.opt(exception=True).warning('[Rerank] 调用失败: {}', exc)
            return None

        # SDK 只回 index（入参 texts 的下标，非业务/Milvus id）+ score；按下标取回 documents[i].id
        out: list[RerankResultVo] = []
        for item in ranked or []:
            idx = int(item['index'])
            # 防御：越界下标无法映射，直接跳过
            if idx < 0 or idx >= len(documents):
                continue
            out.append(
                RerankResultVo(
                    id=documents[idx].id,
                    score=float(item.get('relevance_score', item.get('score', 0.0))),
                )
            )
        logger.info('[Rerank] model={} in={} out={}', adapter.model_code, len(documents), len(out))
        return out

    @classmethod
    async def _load_adapter(cls) -> AiModelConfigModel:
        """加载 document_rerank 适配；未配置或缺关键字段则抛错，提示运营补齐。"""
        adapters = await AiModelFunctionAdapterDao.get_adapters_by_param_id(
            AiModelFunctionAdapterConfig.document_rerank_param_id
        )
        if not adapters:
            raise ServiceException('未配置 document_rerank 模型适配，请联系运营配置')
        adapter = adapters[0]
        if not adapter.model_code or not (adapter.api_key or '').strip():
            raise ServiceException('document_rerank 适配缺少 model_code/api_key，请联系运营配置')
        return adapter

    @classmethod
    def _to_config(cls, adapter: AiModelConfigModel, top_n: int | None) -> RerankModelConfigModel:
        """DB 适配 → 工厂入参；top_n 由本次调用传入，不写死在适配里。"""
        return RerankModelConfigModel(
            model_code=adapter.model_code,
            provider=adapter.provider,
            api_key=adapter.api_key,
            base_url=adapter.base_url,
            top_n=top_n,
        )

    @classmethod
    def _clip(cls, text: str, max_doc_chars: int) -> str:
        """截断过长文档正文，避免超出 rerank 模型单条输入上限。"""
        body = (text or '').strip()
        if len(body) > max_doc_chars:
            return body[:max_doc_chars] + '…'
        return body
