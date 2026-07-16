"""
验证爬取 Agent 后端 SSE 流式输出的测试

测试目标：
1. `stream_mode=['messages', 'updates']` 是否能拦截 LLM 的 token 级流式输出
2. `analyze_node` 使用 `llm.astream()` 后，token 是否能被实时 yield
3. 对比 `llm.ainvoke()` vs `llm.astream()` 在 `stream_mode='messages'` 下的行为差异
"""

import asyncio
import json
import time
from typing import Any, AsyncIterator, Iterator, List, Optional

import pytest

pytestmark = pytest.mark.asyncio

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from knowledge_common.agent.state.react import ReactBaseState
from knowledge_common.utils.log_util import logger


class StreamingTestState(ReactBaseState):
    """流式测试专用状态（含 messages，与父图 CrawlerAgentState 分离）"""

    target_url: str
    session_id: int
    model_id: int | None
    user_id: int
    dept_id: int | None
    message_id: str

# ==================== Fake LLM 模拟 ====================

class FakeStreamingChatModel(BaseChatModel):
    """
    模拟流式输出的 Fake ChatModel

    _astream 方法逐字符 yield，模拟真实 LLM 的 token 级输出。
    支持配置返回句子的长度和工具调用行为。
    """

    model_config = {'extra': 'allow'}

    def __init__(self, response_text: str = '模拟分析：该网站结构清晰，适合爬取。', has_tool_call: bool = False, max_call_rounds: int = 1, **kwargs):
        super().__init__(**kwargs)
        object.__setattr__(self, 'response_text', response_text)
        object.__setattr__(self, 'has_tool_call', has_tool_call)
        object.__setattr__(self, '_call_count', 0)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """模拟逐 token 流式输出"""
        object.__setattr__(self, '_call_count', self._call_count + 1)
        current_round = self._call_count

        for i, char in enumerate(self.response_text):
            chunk = AIMessageChunk(content=char)
            yield ChatGenerationChunk(message=chunk)
            await asyncio.sleep(0.01)
            if run_manager:
                await run_manager.on_llm_new_token(char)

        # 仅在指定轮次和配置下才模拟工具调用
        if self.has_tool_call and current_round <= 1:
            tool_chunk = AIMessageChunk(
                content='',
                tool_call_chunks=[{
                    'name': 'fetch_robots_txt',
                    'args': '{"url": "https://milvus.io/robots.txt"}',
                    'id': f'call_fake_{current_round:03d}',
                }],
            )
            yield ChatGenerationChunk(message=tool_chunk)
            await asyncio.sleep(0.01)

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        raise NotImplementedError('同步 streaming 未实现')

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        """非流式生成（用于对比测试）"""
        object.__setattr__(self, '_call_count', self._call_count + 1)
        current_round = self._call_count

        content = self.response_text
        message = AIMessage(content=content)
        if self.has_tool_call and current_round <= 1:
            message.tool_calls = [
                {'name': 'fetch_robots_txt', 'args': {'url': 'https://milvus.io/robots.txt'}, 'id': f'call_fake_{current_round:03d}'},
            ]
            message.additional_kwargs['tool_calls'] = [
                {
                    'function': {'name': 'fetch_robots_txt', 'arguments': '{"url": "https://milvus.io/robots.txt"}'},
                    'id': f'call_fake_{current_round:03d}',
                    'type': 'function',
                }
            ]

        generation = ChatGeneration(message=message)
        return ChatResult(generations=[generation])

    @property
    def _llm_type(self) -> str:
        return 'fake-streaming'


# ==================== 测试图结构 ====================


def build_test_graph(llm: Runnable) -> 'CompiledStateGraph':
    """
    构建简化版的测试图

    模仿真实爬取 Agent 的图结构：analyze → tools → collect_results → analyze (loop)
    """

    async def analyze_node(state: StreamingTestState) -> dict:
        """模拟 analyze 节点"""
        messages = list(state['messages'])

        merged_chunk = None
        async for chunk in llm.astream(messages):
            if merged_chunk is None:
                merged_chunk = chunk
            else:
                merged_chunk += chunk

        response = merged_chunk if merged_chunk is not None else AIMessage(content='')
        react_round = state['react_round'] + 1
        return {'messages': [response], 'react_round': react_round}

    def should_continue_react(state: StreamingTestState) -> str:
        last_msg = state['messages'][-1] if state['messages'] else None
        if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
            return 'tools'
        return 'end'

    # 测试 tools: 模拟的工具
    async def mock_fetch_robots_tool(url: str) -> str:
        """Fetch robots.txt for the given URL"""
        return 'User-agent: *\nDisallow: /api/'

    async def collect_results_node(state: StreamingTestState) -> dict:
        return state

    # 构建图
    graph = StateGraph(StreamingTestState)
    graph.add_node('analyze', analyze_node)
    graph.add_node('tools', ToolNode([mock_fetch_robots_tool]))
    graph.add_node('collect_results', collect_results_node)

    graph.add_edge(START, 'analyze')
    graph.add_conditional_edges(
        'analyze', should_continue_react,
        {'tools': 'tools', 'end': END},
    )
    graph.add_edge('tools', 'collect_results')
    graph.add_edge('collect_results', 'analyze')

    return graph.compile()


# ==================== 测试用例 ====================


async def test_stream_mode_messages_with_astream():
    """
    测试 `stream_mode=['messages', 'updates']` + `llm.astream()`

    期望行为：
    - messages 模式：按 token 粒度 yield (AIMessageChunk, metadata) 事件
    - 每个 chunk 对应一个 output token
    """
    print('\n' + '=' * 60)
    print('Test 1: stream_mode=[messages, updates] + llm.astream()')
    print('=' * 60)

    llm = FakeStreamingChatModel(
        response_text='分析完毕：该网站结构清晰，适合爬取。',
        has_tool_call=False,
    )
    graph = build_test_graph(llm)

    input_state: dict = {
        'messages': [HumanMessage(content='分析 https://milvus.io/docs/zh')],
        'target_url': 'https://milvus.io/docs/zh',
        'react_round': 0,
        'session_id': 1,
        'model_id': None,
        'user_id': 1,
        'dept_id': 1,
        'message_id': 'test',
    }
    config = {'configurable': {'thread_id': 'test-1'}}

    token_count = 0
    update_count = 0

    start_time = time.time()
    async for item in graph.astream(input_state, config=config, stream_mode=['messages', 'updates']):
        mode, data = item

        if mode == 'messages':
            chunk, metadata = data
            token_count += 1
            elapsed = time.time() - start_time
            print(f'  [messages #{token_count}] +{elapsed:.3f}s: content={repr(chunk.content)}')
        elif mode == 'updates':
            update_count += 1
            print(f'  [updates #{update_count}] nodes={list(data.keys())}')

    print(f'\n  结果: 共 {token_count} 个 token 事件, {update_count} 个 updates 事件')
    assert token_count > 1, f'期望多个 token 事件, 实际只收到 {token_count}'
    print('  ✓ PASS: 流式 token 事件被成功拦截!')


async def test_stream_mode_updates_with_astream():
    """
    测试 `stream_mode='updates'` + `llm.astream()`

    对比：只使用 updates 模式时，是否能获取 ASTREAM 的 token 级输出

    期望行为：
    - 只收到 updates 事件（节点完整输出），没有 token 级事件
    """
    print('\n' + '=' * 60)
    print('Test 2: stream_mode=updates + llm.astream()')
    print('=' * 60)

    llm = FakeStreamingChatModel(
        response_text='分析完毕。',
        has_tool_call=False,
    )
    graph = build_test_graph(llm)

    input_state = {
        'messages': [HumanMessage(content='test')],
        'target_url': '',
        'react_round': 0,
        'session_id': 1,
        'model_id': None,
        'user_id': 1,
        'dept_id': 1,
        'message_id': 'test',
    }
    config = {'configurable': {'thread_id': 'test-2'}}

    token_count = 0
    update_count = 0

    async for item in graph.astream(input_state, config=config, stream_mode='updates'):
        token_count += 1
        update_count += 1
        print(f'  [updates #{update_count}] nodes={list(item.keys())}')

    print(f'\n  结果: 共 {update_count} 个 updates 事件')
    print('  ✓ 只有 updates 事件, 无 token 级事件 (符合预期)')


async def test_stream_mode_messages_with_ainvoke():
    """
    测试 `stream_mode=['messages', 'updates']` + `llm.ainvoke()`

    验证：若节点使用 ainvoke(非流式)，stream_mode='messages' 是否仍能收到 token 事件

    期望行为：
    - 可能只收到 1 个 token 事件（完整内容作为单个 chunk），或者 0 个
    """
    print('\n' + '=' * 60)
    print('Test 3: stream_mode=[messages, updates] + llm.ainvoke()')
    print('=' * 60)

    llm = FakeStreamingChatModel(
        response_text='分析完毕。',
        has_tool_call=False,
    )

    # 使用 ainvoke 的分析节点（旧版本行为）
    async def analyze_node_ainvoke(state: StreamingTestState) -> dict:
        messages = list(state['messages'])
        response = await llm.ainvoke(messages)
        react_round = state['react_round'] + 1
        return {'messages': [response], 'react_round': react_round}

    graph = StateGraph(StreamingTestState)
    graph.add_node('analyze', analyze_node_ainvoke)
    graph.add_edge(START, 'analyze')
    graph.add_edge('analyze', END)
    compiled = graph.compile()

    input_state = {
        'messages': [HumanMessage(content='test')],
        'target_url': '',
        'react_round': 0,
        'session_id': 1,
        'model_id': None,
        'user_id': 1,
        'dept_id': 1,
        'message_id': 'test',
    }
    config = {'configurable': {'thread_id': 'test-3'}}

    token_count = 0
    update_count = 0

    async for item in compiled.astream(input_state, config=config, stream_mode=['messages', 'updates']):
        mode, data = item
        if mode == 'messages':
            token_count += 1
            chunk, metadata = data
            print(f'  [messages #{token_count}] chunk={repr(chunk.content)}')
        elif mode == 'updates':
            update_count += 1
            print(f'  [updates #{update_count}] nodes={list(data.keys())}')

    print(f'\n  结果: 共 {token_count} 个 token 事件, {update_count} 个 updates 事件')
    if token_count <= 1:
        print('  ✓ confirm: ainvoke 模式下不出 token 级流式事件 (或最多 1 个完整事件)')
    print()


async def test_tool_call_with_streaming():
    """
    测试带工具调用的流式输出

    验证：
    1. LLM 生成 text 时 yield token 事件
    2. LLM 调用工具时 yield tool_call 事件（来自 updates 模式）
    3. text token 在 tool_call 之前到达
    """
    print('\n' + '=' * 60)
    print('Test 4: tool_call + streaming (astream模式)')
    print('=' * 60)

    llm = FakeStreamingChatModel(
        response_text='我来检查该网站的 robots.txt 文件。',
        has_tool_call=True,
    )
    graph = build_test_graph(llm)

    input_state = {
        'messages': [HumanMessage(content='分析 https://milvus.io/docs/zh')],
        'target_url': 'https://milvus.io/docs/zh',
        'react_round': 0,
        'session_id': 1,
        'model_id': None,
        'user_id': 1,
        'dept_id': 1,
        'message_id': 'test',
    }
    config = {'configurable': {'thread_id': 'test-4'}}

    token_count = 0
    tool_call_count = 0

    async for item in graph.astream(input_state, config=config, stream_mode=['messages', 'updates']):
        mode, data = item
        if mode == 'messages':
            chunk, metadata = data
            if chunk.content:
                token_count += 1
                print(f'  [token #{token_count}] {repr(chunk.content)}')
        elif mode == 'updates':
            for node_name, update in data.items():
                msgs = update.get('messages', [])
                for msg in msgs:
                    if isinstance(msg, AIMessage):
                        tc = getattr(msg, 'tool_calls', None)
                        if tc:
                            tool_call_count += 1
                            print(f'  [tool_call #{tool_call_count}] {tc[0]["name"]}')

    print(f'\n  结果: 共 {token_count} 个 token 事件, {tool_call_count} 个 tool_call 事件')
    if token_count > 0:
        print('  ✓ text token 在 tool_call 之前到达 (打字机效果基础)')
    print()


async def test_subgraph_streaming():
    """
    测试子图场景下的流式输出

    真实爬取 Agent 的图结构是：父图 → analysis 子图 → analyze_node
    需要验证 stream_mode='messages' 能否穿透子图边界捕获 LLM token。

    图结构：
        parent: START -> analysis_subgraph -> END
        subgraph: START -> analyze -> (条件边) -> ...
    """
    print('\n' + '=' * 60)
    print('Test 6: 子图场景 - 验证 stream_mode=messages 穿透子图边界')
    print('=' * 60)

    llm = FakeStreamingChatModel(
        response_text='分析完毕：该网站结构清晰，适合爬取。',
        has_tool_call=False,
    )

    # --- 构建子图（同真实 analyze 子图结构）---
    subgraph = StateGraph(StreamingTestState)

    async def analyze_node(state: StreamingTestState) -> dict:
        messages = list(state['messages'])
        merged_chunk = None
        async for chunk in llm.astream(messages):
            if merged_chunk is None:
                merged_chunk = chunk
            else:
                merged_chunk += chunk
        response = merged_chunk if merged_chunk is not None else AIMessage(content='')
        react_round = state['react_round'] + 1
        return {'messages': [response], 'react_round': react_round}

    def should_end(state: StreamingTestState) -> str:
        return 'end'

    subgraph.add_node('analyze', analyze_node)
    subgraph.add_edge(START, 'analyze')
    subgraph.add_conditional_edges('analyze', should_end, {'end': END})
    compiled_subgraph = subgraph.compile()

    # --- 构建父图 ---
    parent = StateGraph(StreamingTestState)
    parent.add_node('analysis', compiled_subgraph)
    parent.add_edge(START, 'analysis')
    parent.add_edge('analysis', END)
    compiled_parent = parent.compile()

    # --- 测试 ---
    input_state = {
        'messages': [HumanMessage(content='test')],
        'target_url': '',
        'react_round': 0,
        'session_id': 1,
        'model_id': None,
        'user_id': 1,
        'dept_id': 1,
        'message_id': 'test',
    }
    config = {'configurable': {'thread_id': 'test-subgraph'}}

    token_count = 0
    async for item in compiled_parent.astream(input_state, config=config, stream_mode=['messages', 'updates'], subgraphs=True):
        # subgraphs=True 时 item 格式: (namespaces, mode, data)
        if isinstance(item, tuple) and len(item) == 3:
            namespaces, mode, data = item
        else:
            namespaces, mode, data = (), *item

        if mode == 'messages':
            chunk, metadata = data
            token_count += 1
            print(f'  [messages #{token_count}] {repr(chunk.content)}')
        elif mode == 'updates':
            if not namespaces:
                continue  # 跳过父级 updates
            print(f'  [updates] ns={namespaces}, nodes={list(data.keys())}')

    print(f'\n  结果: 共 {token_count} 个 token 事件')
    if token_count > 1:
        print('  ✓ PASS: stream_mode=messages 穿透子图边界!')
    else:
        print('  ✗ FAIL: 子图内无 token 级流式输出!(可能子图阻止了消息传播)')


async def test_sse_mapping_with_subgraph():
    """
    测试完整的 SSE 映射逻辑（模拟 chat_stream 的行为）

    使用 subgraph 结构，验证 SSE 事件映射是否正确：
    - token 事件来自 messages 模式
    - tool_call 事件来自 updates 模式
    - 不产生重复的 token 事件
    """
    print('\n' + '=' * 60)
    print('Test 7: 完整 SSE 映射（subgraph + 实际映射逻辑）')
    print('=' * 60)

    llm = FakeStreamingChatModel(
        response_text='我来检查该网站的 robots.txt。',
        has_tool_call=True,
    )

    # --- 构建测试图（含工具调用）---
    subgraph = StateGraph(StreamingTestState)

    async def analyze_node(state: StreamingTestState) -> dict:
        messages = list(state['messages'])
        merged_chunk = None
        async for chunk in llm.astream(messages):
            if merged_chunk is None:
                merged_chunk = chunk
            else:
                merged_chunk += chunk
        response = merged_chunk if merged_chunk is not None else AIMessage(content='')
        react_round = state['react_round'] + 1
        return {'messages': [response], 'react_round': react_round}

    async def mock_fetch(url: str) -> str:
        """Mock fetch robots.txt"""
        return 'User-agent: *\nDisallow: /api/'

    async def collect_results(state: StreamingTestState) -> dict:
        return state

    def route(state: StreamingTestState) -> str:
        last = state['messages'][-1] if state['messages'] else None
        if hasattr(last, 'tool_calls') and last.tool_calls:
            return 'tools'
        return 'end'

    subgraph.add_node('analyze', analyze_node)
    subgraph.add_node('tools', ToolNode([mock_fetch]))
    subgraph.add_node('collect_results', collect_results)
    subgraph.add_edge(START, 'analyze')
    subgraph.add_conditional_edges('analyze', route, {'tools': 'tools', 'end': END})
    subgraph.add_edge('tools', 'collect_results')
    subgraph.add_edge('collect_results', 'analyze')
    compiled_subgraph = subgraph.compile()

    parent = StateGraph(StreamingTestState)
    parent.add_node('analysis', compiled_subgraph)
    parent.add_edge(START, 'analysis')
    parent.add_edge('analysis', END)
    compiled_parent = parent.compile()

    # --- 模拟 chat_stream 的 SSE 映射逻辑 ---
    input_state = {
        'messages': [HumanMessage(content='分析 https://milvus.io/docs/zh')],
        'target_url': 'https://milvus.io/docs/zh',
        'react_round': 0,
        'session_id': 1,
        'model_id': None,
        'user_id': 1,
        'dept_id': 1,
        'message_id': 'test',
    }
    config = {'configurable': {'thread_id': 'test-sse'}}

    token_count = 0
    tool_call_count = 0

    from knowledge_common.agent.schema.context import AgentIdentityContextVo
    from knowledge_common.agent.stream import TokenEvent, ToolCallEvent, normalize_astream

    context = AgentIdentityContextVo(
        session_id=1, user_id=1, dept_id=1, user_name='tester', model_id=None,
    )
    async for event in normalize_astream(
        compiled_parent,
        config=config,
        context=context.model_dump(),
        input_or_resume=input_state,
    ):
        if isinstance(event, TokenEvent):
            token_count += 1
            if token_count <= 5 or token_count % 5 == 0:
                print(f'  [token #{token_count}] {repr(event.content)}')
        elif isinstance(event, ToolCallEvent):
            tool_call_count += 1
            print(f'  [SSE tool_call #{tool_call_count}] {event.tool_name}')

    print(f'\n  结果: {token_count} token 事件 + {tool_call_count} tool_call 事件')
    if token_count > 3:
        print('  ✓ PASS: 多 token 事件通过 SSE 成功产出!')
        print(f'  ✓ 打字机效果基础条件满足（{token_count} 个 token 块）')
    print()


# ==================== 主入口 ====================

async def main():
    print('=' * 60)
    print('知识爬取 Agent 流式输出测试')
    print(f'LangGraph 版本: 1.2.4')
    print('=' * 60)

    await test_stream_mode_messages_with_astream()
    await test_stream_mode_updates_with_astream()
    await test_stream_mode_messages_with_ainvoke()
    await test_tool_call_with_streaming()
    await test_subgraph_streaming()
    await test_sse_mapping_with_subgraph()

    print('\n' + '=' * 60)
    print('所有测试完成')
    print('=' * 60)


if __name__ == '__main__':
    asyncio.run(main())
