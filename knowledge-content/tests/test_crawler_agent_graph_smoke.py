"""Crawler graph / planning smoke test（不连 DB/Redis）"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_get_root_graph_direct_supervisor_with_checkpointer():
    from knowledge_content.agents.crawler_agent import graph as graph_module

    mock_checkpointer = MagicMock(name='checkpointer')
    mock_supervisor_compiled = MagicMock(name='deep_supervisor_compiled')

    with (
        patch.object(
            graph_module.Checkpointer,
            'get_checkpointer',
            AsyncMock(return_value=mock_checkpointer),
        ),
        patch.object(
            graph_module,
            'get_deep_supervisor_graph',
            AsyncMock(return_value=mock_supervisor_compiled),
        ) as mock_get_supervisor,
    ):
        compiled = await graph_module.get_root_graph()

    assert compiled is mock_supervisor_compiled
    mock_get_supervisor.assert_awaited_once_with(checkpointer=mock_checkpointer)


@pytest.mark.asyncio
async def test_planning_subgraph_no_ask_user_node():
    from knowledge_content.agents.crawler_agent.workers.planning.graph import get_planning_subgraph

    with patch('knowledge_content.agents.crawler_agent.workers.planning.graph.get_base_chat_model') as mock_model:
        mock_model.return_value = MagicMock()
        compiled = await get_planning_subgraph()
    assert 'ask_user' not in compiled.nodes


@pytest.mark.asyncio
async def test_planning_subgraph_has_create_agent_nodes():
    from knowledge_content.agents.crawler_agent.workers.planning.graph import get_planning_subgraph

    with patch('knowledge_content.agents.crawler_agent.workers.planning.graph.get_base_chat_model') as mock_model:
        mock_model.return_value = MagicMock()
        compiled = await get_planning_subgraph()
    assert {'model', 'tools'}.issubset(set(compiled.nodes.keys()))
