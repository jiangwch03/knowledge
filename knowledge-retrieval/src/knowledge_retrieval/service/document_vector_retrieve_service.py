"""混合检索：Milvus hybrid_search + 业务侧精排 / 父片回填。

Milvus 只返回 ``MilvusSearchHit``；进入业务流水线后转为 ``DocumentVectorRetrieveHitVo``。
"""

from __future__ import annotations

from typing import Any

from knowledge_common.config.env import MilvusConfig
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.milvus import (
    DocumentVectorVo,
    KnowledgeMilvusClient,
    MilvusDenseChannelVo,
    MilvusHybridSearchRequestVo,
    MilvusSearchHit,
    MilvusSparseChannelVo,
)
from knowledge_common.service.document_embedding_service import DocumentEmbeddingService
from knowledge_common.vo.user_vo import CurrentUserModel
from knowledge_retrieval.enums.release_tag_enum import ReleaseTag
from knowledge_retrieval.mapper.dao.document_segment_ro_dao import DocumentSegmentRoDao
from knowledge_retrieval.service.milvus_data_scope import MilvusDataScopeBuilder
from knowledge_retrieval.service.rerank_service import RerankService
from knowledge_retrieval.vo.document_vector_retrieve_vo import (
    DocumentVectorRetrieveHitVo,
    DocumentVectorRetrieveRequestVo,
    DocumentVectorRetrieveResponseVo,
)
from knowledge_retrieval.vo.rerank_vo import RerankDocumentVo


class DocumentVectorRetrieveService:
    """文档向量检索服务（dense ANN + BM25 + RRF）。"""

    @classmethod
    async def hybrid_retrieve(
        cls,
        request: DocumentVectorRetrieveRequestVo,
        current_user: CurrentUserModel,
    ) -> DocumentVectorRetrieveResponseVo:
        """混合检索：dense ANN + BM25 + RRF（可选精排），返回按相关性降序的命中列表。"""
        query = request.query.strip()
        filter_expr = await cls._build_filter(request, current_user)
        query_vector = await DocumentEmbeddingService.embed_query(query)

        # 召回池放大：给精排留足候选，下限 20
        candidate_limit = max(request.top_k * 4, 20)
        milvus_hits = await cls._hybrid_search(
            query_vector=query_vector,
            query_text=query,
            filter_expr=filter_expr,
            limit=candidate_limit,
            score_threshold=request.score_threshold,
            rrf_k=request.rrf_k,
        )
        # 没有命中，直接返回空列表
        if not milvus_hits:
            return DocumentVectorRetrieveResponseVo(query=query, hits=[])

        # Milvus 对象 → 业务对象
        candidates = [DocumentVectorRetrieveHitVo.from_milvus_hit(h) for h in milvus_hits]

        if request.enable_rerank:
            candidates = await cls._rerank_candidates(query, candidates)
        # 精排后 top_k
        filtered = candidates[: request.top_k]
        # 子片命中时回填父片全文
        if request.expand_parent and filtered:
            filtered = await cls._expand_parents(filtered)
        # 返回
        return DocumentVectorRetrieveResponseVo(
            query=query,
            hits=filtered,
        )

    @classmethod
    async def _rerank_candidates(
        cls,
        query: str,
        candidates: list[DocumentVectorRetrieveHitVo],
    ) -> list[DocumentVectorRetrieveHitVo]:
        """精排候选并按精排顺序回填 score。"""
        ranked = await RerankService.rerank(
            query,
            [cls._to_rerank_doc(h) for h in candidates],
            top_n=len(candidates),
        )
        if not ranked:
            raise ServiceException('精排失败或结果为空')
        # 精排只返回 id+score；按精排顺序回填到原命中，覆盖 score
        # 映射：id→命中 字典
        by_id = {h.id: h for h in candidates}
        merged: list[DocumentVectorRetrieveHitVo] = []
        for item in ranked:
            hit = by_id.get(item.id)
            if hit is None:
                continue
            # 浅拷贝 不改原对象
            merged.append(hit.model_copy(update={'score': item.score}))

        if not merged:
            raise ServiceException('精排结果为空')
        # 返回精排结果，覆盖原命中
        return merged

    @classmethod
    def _to_rerank_doc(cls, hit: DocumentVectorRetrieveHitVo) -> RerankDocumentVo:
        """从业务命中抽取精排 id + 正文。"""
        text = (hit.text or '').strip()
        if not text:
            text = (hit.doc_title or hit.chunk_id or hit.id or '')[:200]
        return RerankDocumentVo(id=hit.id, text=text)

    @classmethod
    async def _build_filter(cls, request: DocumentVectorRetrieveRequestVo, current_user: CurrentUserModel) -> str:
        """拼装 Milvus filter：release_tag + 可选 task_id + 用户数据权限。"""
        parts: list[str] = []
        tag = request.release_tag or ReleaseTag.PROD
        parts.append(f'release_tag == "{tag.value}"')
        if request.task_id is not None:
            parts.append(f'task_id == {int(request.task_id)}')
        scope = await MilvusDataScopeBuilder.build_filter(current_user)
        if scope:
            parts.append(f'({scope})')
        return ' && '.join(parts)

    @classmethod
    def _dense_search_params(cls, score_threshold: float) -> dict[str, Any]:
        """稠密路 COSINE 参数；score_threshold>0 时作为 range search 下界（radius）。"""
        params: dict[str, Any] = {'metric_type': 'COSINE'}
        if score_threshold > 0:
            params['params'] = {
                'radius': float(score_threshold),
                'range_filter': 1.0,
            }
        return params

    @classmethod
    async def _hybrid_search(
        cls,
        *,
        query_vector: list[float],
        query_text: str,
        filter_expr: str,
        limit: int,
        score_threshold: float,
        rrf_k: int,
    ) -> list[MilvusSearchHit[DocumentVectorVo]]:
        """Milvus 原生 hybrid_search（dense + BM25 + RRFRanker）。"""
        milvus = KnowledgeMilvusClient()
        return await milvus.hybrid_search(
            MilvusHybridSearchRequestVo(
                collection=MilvusConfig.document_vector_collection,
                vo_cls=DocumentVectorVo,
                dense=MilvusDenseChannelVo(
                    vector=query_vector,
                    search_params=cls._dense_search_params(score_threshold),
                    limit=limit,
                ),
                sparse=MilvusSparseChannelVo(
                    text=query_text,
                    search_params={'metric_type': 'BM25'},
                    limit=limit,
                ),
                limit=limit,
                filter_expr=filter_expr,
                rrf_k=rrf_k,
            )
        )

    @classmethod
    async def _expand_parents(
        cls,
        hits: list[DocumentVectorRetrieveHitVo],
    ) -> list[DocumentVectorRetrieveHitVo]:
        """有 parent_chunk_id 时用父片全文替换 text；chunk_id / parent_chunk_id 不变。"""
        parent_ids = [h.parent_chunk_id for h in hits if h.parent_chunk_id]
        # 没有父分片，直接返回
        if not parent_ids:
            return hits
        # 获取父分片全文
        parents = await DocumentSegmentRoDao.get_by_chunk_ids(parent_ids)
        # 映射：parent_chunk_id→父分片 字典
        by_id = {h.chunk_id: h for h in parents}
        # 遍历命中，有父分片且父分片全文不为空，则替换 text
        expanded: list[DocumentVectorRetrieveHitVo] = []
        for hit in hits:
            parent = parents.get(hit.parent_chunk_id or '')
            if parent :
                expanded.append(hit.model_copy(update={'text': parent.text}))
                continue
            # 没有父分片，直接添加
            expanded.append(hit)
        # 返回
        return expanded
