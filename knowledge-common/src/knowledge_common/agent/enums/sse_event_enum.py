from enum import Enum


class AgentSseEvent(str, Enum):
    """Agent SSE 事件名（与前端 parseSseBlock 对齐）。"""

    TOKEN = 'token'  # LLM 正文分片（打字机）
    TOOL_CALL = 'tool_call'  # 工具调用卡片（call / result 阶段见 AgentToolCallPhase）
    BUSINESS = 'business'  # 业务旁路统一事件（载荷在 data，由前端按结构分流）


class AgentToolCallPhase(str, Enum):
    """tool_call SSE 的阶段：call 建卡，result 更新同一张卡。"""

    CALL = 'call'  # 工具调用开始
    RESULT = 'result'  # 工具调用结果
