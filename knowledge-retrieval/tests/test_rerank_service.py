"""RerankService：工厂收口 + 降级单测。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_common.exceptions.exception import ServiceException
from knowledge_retrieval.service.rerank_service import RerankService
from knowledge_retrieval.vo.rerank_vo import RerankDocumentVo


@pytest.mark.asyncio
async def test_rerank_raises_without_adapter():
    with (
        patch.object(
            RerankService,
            '_load_adapter',
            new=AsyncMock(side_effect=ServiceException('未配置 document_rerank 模型适配，请联系运营配置')),
        ),
        pytest.raises(ServiceException, match='document_rerank'),
    ):
        await RerankService.rerank('q', [RerankDocumentVo(id='a', text='hello')])


@pytest.mark.asyncio
async def test_rerank_via_dashscope_compressor():
    adapter = type(
        'A',
        (),
        {
            'model_code': 'qwen3-rerank',
            'api_key': 'sk-test',
            'base_url': 'https://dashscope.aliyuncs.com/api/v1',
            'provider': 'DashScope',
        },
    )()
    documents = [
        RerankDocumentVo(id='a', text='irrelevant'),
        RerankDocumentVo(id='b', text='relevant answer'),
    ]
    compressor = MagicMock()
    compressor.rerank.return_value = [
        {'index': 1, 'relevance_score': 0.95},
        {'index': 0, 'relevance_score': 0.1},
    ]

    with (
        patch.object(RerankService, '_load_adapter', new=AsyncMock(return_value=adapter)),
        patch(
            'knowledge_retrieval.service.rerank_service.RagConfigService.get_rerank_max_doc_chars',
            new=AsyncMock(return_value=4000),
        ),
        patch(
            'knowledge_retrieval.service.rerank_service.DashScopeModelFactory.create_rerank_compressor',
            return_value=compressor,
        ),
    ):
        out = await RerankService.rerank('q', documents)

    assert out is not None
    assert [r.id for r in out] == ['b', 'a']
    assert out[0].score == 0.95
    compressor.rerank.assert_called_once()


@pytest.mark.asyncio
async def test_rerank_factory_failure_returns_none():
    adapter = type(
        'A',
        (),
        {
            'model_code': 'qwen3-rerank',
            'api_key': 'sk-test',
            'base_url': 'https://dashscope.aliyuncs.com/api/v1',
            'provider': 'DashScope',
        },
    )()
    with (
        patch.object(RerankService, '_load_adapter', new=AsyncMock(return_value=adapter)),
        patch(
            'knowledge_retrieval.service.rerank_service.RagConfigService.get_rerank_max_doc_chars',
            new=AsyncMock(return_value=4000),
        ),
        patch(
            'knowledge_retrieval.service.rerank_service.DashScopeModelFactory.create_rerank_compressor',
            side_effect=RuntimeError('boom'),
        ),
    ):
        out = await RerankService.rerank('q', [RerankDocumentVo(id='a', text='x')])
    assert out is None
