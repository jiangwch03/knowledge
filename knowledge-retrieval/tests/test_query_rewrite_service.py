"""QueryRewriteService 单测：提示词缺失/LLM 失败降级、历史拼装。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge_common.agent.enums.message_role_enum import MessageRoleLangchain
from knowledge_retrieval.service.query_rewrite_service import QueryRewriteService, _RewriteLlmOut
from knowledge_retrieval.vo.query_rewrite_vo import QueryRewriteRequestVo


def _msg(role: str, content: str):
    return SimpleNamespace(role=role, content=content)


def test_build_user_prompt_with_history():
    history = [
        _msg(MessageRoleLangchain.HUMAN.value, 'HNSW 的 M 怎么设？'),
        _msg(MessageRoleLangchain.AI.value, '通常从 16 起调'),
    ]
    text = QueryRewriteService._build_user_prompt('那 efConstruction 呢？', history)
    assert 'HNSW 的 M 怎么设？' in text
    assert '当前用户问题：那 efConstruction 呢？' in text


def test_build_user_prompt_without_history():
    text = QueryRewriteService._build_user_prompt('Milvus 咋配？', [])
    assert '无历史对话' in text
    assert 'Milvus 咋配？' in text


@pytest.mark.asyncio
async def test_rewrite_missing_prompt_returns_original():
    with patch(
        'knowledge_retrieval.service.query_rewrite_service.prompt_config.get_system_prompt',
        return_value=None,
    ):
        out = await QueryRewriteService.rewrite(
            QueryRewriteRequestVo(question='那呢？', history=[])
        )
    assert out == '那呢？'


@pytest.mark.asyncio
async def test_rewrite_llm_success():
    llm = MagicMock()
    runnable = MagicMock()
    runnable.ainvoke = AsyncMock(return_value=_RewriteLlmOut(query='HNSW 的 efConstruction 如何设置？'))
    llm.with_structured_output.return_value = runnable

    with (
        patch(
            'knowledge_retrieval.service.query_rewrite_service.prompt_config.get_system_prompt',
            return_value='rewrite system',
        ),
        patch(
            'knowledge_retrieval.service.query_rewrite_service.get_base_chat_model',
            new=AsyncMock(return_value=llm),
        ),
    ):
        out = await QueryRewriteService.rewrite(
            QueryRewriteRequestVo(
                question='那呢？',
                history=[
                    _msg(MessageRoleLangchain.HUMAN.value, 'HNSW 的 M 怎么设？'),
                    _msg(MessageRoleLangchain.AI.value, '从 16 起'),
                ],
            )
        )
    assert out == 'HNSW 的 efConstruction 如何设置？'


@pytest.mark.asyncio
async def test_rewrite_llm_failure_returns_original():
    with (
        patch(
            'knowledge_retrieval.service.query_rewrite_service.prompt_config.get_system_prompt',
            return_value='rewrite system',
        ),
        patch(
            'knowledge_retrieval.service.query_rewrite_service.get_base_chat_model',
            new=AsyncMock(side_effect=RuntimeError('boom')),
        ),
    ):
        out = await QueryRewriteService.rewrite(
            QueryRewriteRequestVo(question='口语咋整 HNSW', history=[])
        )
    assert out == '口语咋整 HNSW'
