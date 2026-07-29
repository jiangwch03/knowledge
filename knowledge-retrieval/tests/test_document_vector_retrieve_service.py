"""DocumentVectorRetrieveService 单测：稠密 range 参数、空命中、父片回填字段。"""

from __future__ import annotations

import pytest

from knowledge_common.milvus import DocumentVectorVo, MilvusSearchHit
from knowledge_retrieval.service.document_vector_retrieve_service import DocumentVectorRetrieveService
from knowledge_retrieval.vo.document_vector_retrieve_vo import (
    DocumentVectorRetrieveHitVo,
    DocumentVectorRetrieveRequestVo,
)


def test_dense_search_params_applies_radius():
    params = DocumentVectorRetrieveService._dense_search_params(0.5)
    assert params['metric_type'] == 'COSINE'
    assert params['params']['radius'] == 0.5
    assert params['params']['range_filter'] == 1.0


def test_dense_search_params_skips_radius_when_zero():
    params = DocumentVectorRetrieveService._dense_search_params(0.0)
    assert params == {'metric_type': 'COSINE'}
    assert 'params' not in params


def test_search_request_rejects_blank_query():
    with pytest.raises(Exception):
        DocumentVectorRetrieveRequestVo(query='   ')


def test_from_milvus_hit_maps_business_fields():
    milvus_hit = MilvusSearchHit(
        id='emb-1',
        distance=0.42,
        entity=DocumentVectorVo(
            id='emb-1',
            chunk_id='child-1',
            parent_chunk_id='parent-1',
            text='t',
            doc_title='title',
        ),
    )
    hit = DocumentVectorRetrieveHitVo.from_milvus_hit(milvus_hit)
    assert hit.id == 'emb-1'
    assert hit.score == 0.42
    assert hit.chunk_id == 'child-1'
    assert hit.parent_chunk_id == 'parent-1'


def test_from_milvus_hit_empty_parent_becomes_none():
    milvus_hit = MilvusSearchHit(
        id='emb-2',
        distance=0.1,
        entity=DocumentVectorVo(id='emb-2', chunk_id='leaf-1', parent_chunk_id='', text='t'),
    )
    hit = DocumentVectorRetrieveHitVo.from_milvus_hit(milvus_hit)
    assert hit.parent_chunk_id is None


@pytest.mark.asyncio
async def test_expand_parent_fields(monkeypatch):
    class Seg:
        def __init__(self, chunk_id, parent_chunk_id=None, text=''):
            self.chunk_id = chunk_id
            self.parent_chunk_id = parent_chunk_id
            self.text = text

    async def fake_get(chunk_ids):
        data = {
            'parent-1': Seg('parent-1', None, 'PARENT FULL TEXT'),
        }
        return {cid: data[cid] for cid in chunk_ids if cid in data}

    monkeypatch.setattr(
        'knowledge_retrieval.mapper.dao.document_segment_ro_dao.DocumentSegmentRoDao.get_by_chunk_ids',
        fake_get,
    )

    hits = [
        DocumentVectorRetrieveHitVo(
            id='emb-1',
            score=0.7,
            chunk_id='child-1',
            parent_chunk_id='parent-1',
            text='child text',
        )
    ]

    expanded = await DocumentVectorRetrieveService._expand_parents(hits)
    assert expanded[0].text == 'PARENT FULL TEXT'
    assert expanded[0].chunk_id == 'child-1'
    assert expanded[0].parent_chunk_id == 'parent-1'
