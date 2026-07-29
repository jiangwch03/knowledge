"""
Agent astream 归一化

把 LangGraph astream 的原始事件流，归一化为「带来源标记的语义事件」，供各业务
Agent 服务统一消费（各自决定落库 / SSE / 聚合等处理）。
"""

from knowledge_common.agent.stream.events import (
    SOURCE_SUBAGENT,
    SOURCE_SUPERVISOR,
    AITextEvent,
    BusinessSseEvent,
    HumanMessageEvent,
    NormalizedEvent,
    PlainMessageEvent,
    SystemMessageEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)
from knowledge_common.agent.stream.normalizer import (
    STREAM_MODE_CUSTOM,
    STREAM_MODE_MESSAGES,
    STREAM_MODE_UPDATES,
    normalize_astream,
)

__all__ = [
    'SOURCE_SUPERVISOR',
    'SOURCE_SUBAGENT',
    'NormalizedEvent',
    'TokenEvent',
    'AITextEvent',
    'ToolCallEvent',
    'ToolResultEvent',
    'SystemMessageEvent',
    'HumanMessageEvent',
    'PlainMessageEvent',
    'BusinessSseEvent',
    'STREAM_MODE_MESSAGES',
    'STREAM_MODE_UPDATES',
    'STREAM_MODE_CUSTOM',
    'normalize_astream',
]
