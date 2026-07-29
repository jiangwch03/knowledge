"""Rerank 真实联调：读库 document_rerank 适配，经 LangChain DashScopeRerank 打一枪。"""

from __future__ import annotations

import pytest

from knowledge_common.common.transactional import async_session_scope
from knowledge_retrieval.service.rerank_service import RerankService
from knowledge_retrieval.vo.rerank_vo import RerankDocumentVo

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_rerank_live_dashscope_orders_relevant_first():
    """需要：本地 DB 已配 document_rerank + 有效 DashScope Key；可出网。"""
    query = 'Milvus 里 HNSW 的 M 参数怎么设置？'
    documents = [
        RerankDocumentVo(id='noise', text='今天天气不错，适合出去散步吃饭。'),
        RerankDocumentVo(
            id='relevant',
            text=(
                'HNSW 索引的 M 参数控制每个节点的最大出边数。'
                'Milvus 中常用取值从 16 起调，增大 M 通常提高召回并增加内存。'
            ),
        ),
        RerankDocumentVo(id='weak', text='Milvus 支持多种索引类型，包括 IVF_FLAT 与 DISKANN。'),
    ]

    async with async_session_scope():
        out = await RerankService.rerank(query, documents, top_n=3)

    assert out is not None, '精排返回 None：检查 Key/网络/模型 qwen3-rerank'
    assert len(out) >= 1
    ids = [r.id for r in out]
    assert 'relevant' in ids
    assert ids.index('relevant') < ids.index('noise')
    assert out[0].score >= out[-1].score
    print('rerank_order=', [(r.id, round(float(r.score), 4)) for r in out])
