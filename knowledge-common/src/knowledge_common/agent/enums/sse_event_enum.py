from enum import Enum


class AgentSseEvent(str, Enum):
    """Agent SSE 事件名（与前端 parseSseBlock 对齐）。"""

    TOKEN = 'token'
    TOOL_CALL = 'tool_call'


class AgentToolCallPhase(str, Enum):
    """tool_call SSE 的阶段：call 建卡，result 更新同一张卡。"""

    CALL = 'call'
    RESULT = 'result'
