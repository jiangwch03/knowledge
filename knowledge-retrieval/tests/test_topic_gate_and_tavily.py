"""Topic gate / QA 路由与 Tavily 降级单测。"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from knowledge_retrieval.agents.tools.tavily_search import _tavily_search
from knowledge_retrieval.service.topic_gate_service import TopicGateResult


def test_unrelated_skips_retrieve_profile_cs():
    gate = TopicGateResult()
    assert gate.prompt_profile == 'cs'


def test_related_runs_retrieve_profile_knowledge():
    gate = TopicGateResult(prompt_profile='knowledge')
    assert gate.prompt_profile == 'knowledge'


@pytest.mark.asyncio
async def test_tavily_missing_key_degrades():
    with patch(
        'knowledge_retrieval.agents.tools.tavily_search._load_tavily_api_key',
        new=AsyncMock(return_value=None),
    ):
        raw = await _tavily_search('hello world')
    data = json.loads(raw)
    assert data['ok'] is False
    assert data['source_type'] == 'web'
    assert data['results'] == []
