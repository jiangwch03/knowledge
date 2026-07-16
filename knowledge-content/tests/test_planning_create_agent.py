"""
Planning create_agent demo / 回归测试

验证：
  1. create_agent 图结构（model + tools）
  2. dynamic_prompt 按 state 渲染 system prompt
  3. wrap_model_call 按 context.model_id 换模型
  4. subgraphs=True + stream_mode=messages 下 AIMessageChunk 穿透
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelRequest, dynamic_prompt
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import tool
from pydantic import ConfigDict

from knowledge_common.agent.schema.context import AgentIdentityContext
from knowledge_common.config.env import CrawlerAgentConfig
from knowledge_content.agents.middleware.crawler_model_middleware import CrawlerModelMiddleware
from knowledge_content.agents.middleware.planning_middleware import planning_system_prompt
from knowledge_content.agents.states.crawler_planning_state import PlanningState


class _DemoChatModel(BaseChatModel):
    """支持 bind_tools + token 级 astream 的最小 ChatModel（仅测试用）"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    responses: list[str | AIMessage]
    label: str = 'default'

    @property
    def _llm_type(self) -> str:
        return 'demo-chat-model'

    def bind_tools(self, tools: list, **kwargs: Any) -> _DemoChatModel:
        return self.model_copy(deep=True)

    def _next_message(self) -> AIMessage:
        if not self.responses:
            return AIMessage(content='done')
        raw = self.responses.pop(0)
        return AIMessage(content=raw) if isinstance(raw, str) else raw

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._next_message())])

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        message = self._next_message()
        text = message.content if isinstance(message.content, str) else str(message.content)
        chunk_id = message.id or 'demo-chunk'
        for char in text:
            yield ChatGenerationChunk(message=AIMessageChunk(content=char, id=chunk_id))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        for chunk in self._stream(messages, stop=stop, run_manager=run_manager, **kwargs):
            yield chunk


@tool
def demo_fetch_page(url: str) -> str:
    """抓取页面（demo）"""
    return f'page:{url}'


@pytest.fixture
def mock_planning_prompt():
    with patch('knowledge_content.agents.middleware.planning_middleware.prompt_config') as mock_cfg:
        mock_cfg.get_system_prompt.return_value = (
            'url={target_url}'
        )
        yield mock_cfg


def _build_demo_planning_agent(
    model: _DemoChatModel,
    *,
    with_model_middleware: bool = False,
) -> Any:
    middleware: list = [
        planning_system_prompt,
        ModelCallLimitMiddleware(
            run_limit=CrawlerAgentConfig.crawler_agent_max_react_rounds,
            exit_behavior='end',
        ),
    ]
    if with_model_middleware:
        middleware.insert(1, CrawlerModelMiddleware())

    return create_agent(
        model=model,
        tools=[demo_fetch_page],
        state_schema=PlanningState,
        context_schema=AgentIdentityContext,
        middleware=middleware,
        name='planning_agent',
    )


@pytest.mark.asyncio
async def test_planning_create_agent_graph_nodes():
    """create_agent 编译后包含 model / tools 节点"""
    agent = _build_demo_planning_agent(_DemoChatModel(responses=['ok'], label='default'))
    assert {'model', 'tools'}.issubset(set(agent.nodes.keys()))


@pytest.mark.asyncio
async def test_planning_dynamic_system_prompt_from_state():
    """dynamic_prompt：失败信息等业务字段可从 state 注入；目标 URL 以委派描述为准"""
    captured: list[str] = []

    @dynamic_prompt
    def capture_prompt(request: ModelRequest) -> str:
        from knowledge_content.agents.middleware.planning_middleware import (
            _render_planning_system_prompt,
        )

        prompt = _render_planning_system_prompt(request.state)
        captured.append(prompt)
        return prompt

    agent = create_agent(
        model=_DemoChatModel(responses=['strategy ready']),
        tools=[demo_fetch_page],
        state_schema=PlanningState,
        middleware=[capture_prompt],
        name='planning_agent',
    )

    with patch('knowledge_content.agents.middleware.planning_middleware.prompt_config') as mock_cfg:
        mock_cfg.get_system_prompt.return_value = (
            '{failed_reason_input}'
        )
        await agent.ainvoke({
            'messages': [HumanMessage(content='分析站点 https://example.com')],
            'failed_reason': '页面超时',
        })

    assert captured
    assert '页面超时' in captured[0]


@pytest.mark.asyncio
async def test_planning_model_middleware_swaps_by_model_id(mock_planning_prompt):
    """wrap_model_call：按 context.model_id 替换 ChatModel"""
    default_model = _DemoChatModel(responses=['from-default'], label='default')
    alt_model = _DemoChatModel(responses=['from-alt'], label='alt')

    resolver = AsyncMock(side_effect=lambda model_id: alt_model if model_id == 99 else default_model)

    agent = _build_demo_planning_agent(default_model, with_model_middleware=True)

    with patch(
        'knowledge_content.agents.middleware.crawler_model_middleware.get_base_chat_model',
        resolver,
    ):
        result = await agent.ainvoke(
            {
                'messages': [HumanMessage(content='hi')],
            },
            context={
                'model_id': 99,
                'session_id': 1,
                'user_id': 1,
                'dept_id': None,
                'user_name': 'test',
            },
        )

    resolver.assert_awaited()
    assert result['messages'][-1].content == 'from-alt'


@pytest.mark.asyncio
async def test_planning_astream_emits_ai_message_chunks(mock_planning_prompt):
    """subgraphs=True + messages 模式：Planning 子图内逐 token 穿透 AIMessageChunk"""
    agent = _build_demo_planning_agent(
        _DemoChatModel(responses=['hello-stream'], label='stream-demo'),
    )

    token_chunks: list[str] = []
    async for item in agent.astream(
        {
            'messages': [HumanMessage(content='stream please')],
            'target_url': 'https://example.com',
        },
        stream_mode=['messages'],
        subgraphs=True,
    ):
        if isinstance(item, tuple) and len(item) == 3:
            _namespaces, mode, data = item
        else:
            _namespaces, mode, data = (), *item

        if mode != 'messages':
            continue
        chunk, _meta = data
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            token_chunks.append(chunk.content)

    assert token_chunks
    assert ''.join(token_chunks) == 'hello-stream'


@pytest.mark.asyncio
async def test_planning_dynamic_prompt_injects_crawl_config():
    """state.crawl_config / target_url 须注入 planning system prompt"""
    captured: list[str] = []

    @dynamic_prompt
    def capture_prompt(request: ModelRequest) -> str:
        from knowledge_content.agents.middleware.planning_middleware import (
            _render_planning_system_prompt,
        )

        prompt = _render_planning_system_prompt(request.state)
        captured.append(prompt)
        return prompt

    agent = create_agent(
        model=_DemoChatModel(responses=['strategy ready']),
        tools=[demo_fetch_page],
        state_schema=PlanningState,
        middleware=[capture_prompt],
        name='planning_agent',
    )

    with patch('knowledge_content.agents.middleware.planning_middleware.prompt_config') as mock_cfg:
        mock_cfg.get_system_prompt.return_value = (
            '{target_url_input}\n{crawl_config_input}'
        )
        await agent.ainvoke({
            'messages': [HumanMessage(content='按已有配置微调')],
            'target_url': 'https://milvus.io/docs/zh/',
            'crawl_config': {'browser_config': {'headless': True}},
        })

    assert captured
    assert 'https://milvus.io/docs/zh/' in captured[0]
    assert 'headless' in captured[0]


@pytest.mark.asyncio
async def test_planning_agent_exits_without_tool_calls(mock_planning_prompt):
    """无 tool_calls 时正常 END（NEED_USER_INPUT 等经 messages 透传）"""
    agent = _build_demo_planning_agent(
        _DemoChatModel(responses=['NEED_USER_INPUT: 请提供 Cookie']),
    )
    result = await agent.ainvoke({
        'messages': [HumanMessage(content='分析')],
    })
    last = result['messages'][-1]
    assert 'NEED_USER_INPUT' in last.content
    assert not getattr(last, 'tool_calls', None)

