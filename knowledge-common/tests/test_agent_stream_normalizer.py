"""归一化层 AIMessage 文本提取回归。"""

from langchain_core.messages import AIMessage

from langchain_core.messages import AIMessageChunk

from knowledge_common.agent.stream.normalizer import (
    _decompose_ai_message,
    _extract_ai_text,
    _extract_chunk_text,
    _normalize_token,
)
from knowledge_common.agent.stream import SOURCE_SUPERVISOR, AITextEvent


def test_extract_ai_text_strips_trailing_newlines_from_string_content():
    msg = AIMessage(
        content='我来查看一下当前正在运行的任务。\n\n\n\n',
        tool_calls=[{'name': 'list_actionable_crawl_tasks', 'args': {}, 'id': 'call_1'}],
    )
    assert _extract_ai_text(msg) == '我来查看一下当前正在运行的任务。'


def test_extract_ai_text_strips_trailing_newlines_from_content_blocks():
    msg = AIMessage(
        content=[
            {'type': 'text', 'text': '我来查看一下当前正在运行的任务。'},
            {'type': 'text', 'text': '\n'},
            {'type': 'text', 'text': '\n'},
            {'type': 'text', 'text': '\n'},
            {'type': 'text', 'text': '\n'},
        ],
        tool_calls=[{'name': 'list_actionable_crawl_tasks', 'args': {}, 'id': 'call_1'}],
    )
    assert _extract_ai_text(msg) == '我来查看一下当前正在运行的任务。'


def test_extract_chunk_text_from_content_blocks():
    chunk = AIMessageChunk(content=[{'type': 'text', 'text': '你好'}])
    assert _extract_chunk_text(chunk) == '你好'


def test_normalize_token_uses_text_not_raw_content_blocks():
    chunk = AIMessageChunk(content=[{'type': 'text', 'text': '\n'}])
    event = _normalize_token((chunk, {}), 'supervisor', None)
    assert event is not None
    assert event.content == '\n'


def test_normalize_token_skips_blacklisted_langgraph_node():
    chunk = AIMessageChunk(content='{"query": "你好"}')
    event = _normalize_token(
        (chunk, {'langgraph_node': 'QueryRewriteMiddleware.before_agent'}),
        'supervisor',
        None,
        skip_token_nodes=frozenset({'QueryRewriteMiddleware.before_agent'}),
    )
    assert event is None


def test_normalize_token_keeps_model_node_when_middleware_blacklisted():
    chunk = AIMessageChunk(content='您好，我是知识库客服。')
    event = _normalize_token(
        (chunk, {'langgraph_node': 'model'}),
        'supervisor',
        None,
        skip_token_nodes=frozenset({
            'QueryRewriteMiddleware.before_agent',
            'TopicGateMiddleware.before_agent',
        }),
    )
    assert event is not None
    assert event.content == '您好，我是知识库客服。'


def test_normalize_token_keeps_when_skip_empty():
    chunk = AIMessageChunk(content='{"related": false}')
    event = _normalize_token(
        (chunk, {'langgraph_node': 'TopicGateMiddleware.before_agent'}),
        'supervisor',
        None,
        skip_token_nodes=frozenset(),
    )
    assert event is not None
    assert event.content == '{"related": false}'


def test_decompose_ai_message_keeps_internal_newlines_only():
    msg = AIMessage(content='第一行\n\n第二行\n\n\n')
    events = _decompose_ai_message(msg, SOURCE_SUPERVISOR, None)
    assert len(events) == 1
    assert isinstance(events[0], AITextEvent)
    assert events[0].content == '第一行\n\n第二行'
