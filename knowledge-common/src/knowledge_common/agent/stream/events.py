"""
astream 归一化事件类型（业务语义 / 前端聊天框对齐）

把 LangGraph astream 的原始事件流，归一化为一组「业务语义事件」——每个事件都对应
前端聊天框里的一种展现（文本气泡 / 工具卡片 call 阶段 / 工具卡片 result 阶段）。
抽象层已经把 langchain 的 AIMessage / ToolMessage 拆解成扁平字段，业务侧无需再碰
原始消息对象，也无需自己去合并「工具调用」与「工具结果」。

来源（source）由 astream 的 namespaces 判定：
- SOURCE_SUPERVISOR：父图（主聊天框），agent_ns=None
- SOURCE_SUBAGENT ：子图（独立聊天框），agent_ns 为该子图的稳定分组 id

一条 AIMessage 可能同时含文本与多个工具调用，故归一化后可拆成多个事件。
"""

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage

# ── 消息来源，供业务把父图 / 子图分派到不同处理路径 ──
SOURCE_SUPERVISOR = 'supervisor'   # 父图（主聊天框）
SOURCE_SUBAGENT = 'subagent'       # 子图（独立聊天框）


@dataclass
class NormalizedEvent:
    """归一化事件基类：所有事件都带来源标记。"""

    source: str            # 标记是子图还是父图 SOURCE_SUPERVISOR / SOURCE_SUBAGENT
    agent_ns: str | None   # 子图分组 id；父图为 None


@dataclass
class TokenEvent(NormalizedEvent):
    """messages 模式：LLM 执行过程中逐 token 推送的分片（打字机），与 updates 并行产出。"""

    content: str


@dataclass
class AITextEvent(NormalizedEvent):
    """
    updates 模式：节点执行完毕时吐出的完整 AIMessage 文本。

    与 TokenEvent 来自同一次 LLM 调用（messages 推分片、updates 推整句），
    业务侧通常 TokenEvent 负责推前端打字机，AITextEvent 负责落库，避免重复推文本。
    """

    content: str


@dataclass
class ToolCallEvent(NormalizedEvent):
    """工具调用（卡片 call 阶段）：已从 AIMessage.tool_calls 抠出的扁平字段。"""

    tool_call_id: str
    tool_name: str
    tool_args: dict[str, Any]


@dataclass
class ToolResultEvent(NormalizedEvent):
    """工具结果（卡片 result 阶段）：与 ToolCallEvent 按 tool_call_id 合并成一张卡片。"""

    tool_call_id: str
    tool_name: str
    content: str


@dataclass
class SystemMessageEvent(NormalizedEvent):
    """系统消息：content 为原始文本（是否展示 / 落库由业务决定）。"""

    content: str


@dataclass
class HumanMessageEvent(NormalizedEvent):
    """用户消息：content 为原始文本（脱敏等处理由业务决定）。"""

    content: str


@dataclass
class PlainMessageEvent(NormalizedEvent):
    """兜底事件：上述未覆盖的其它消息类型，保留原始 message 交业务自行处理。"""

    message: BaseMessage


@dataclass
class BusinessSseEvent(NormalizedEvent):
    """
    业务旁路事件（LangGraph stream_mode=custom ← get_stream_writer）。

    由图内 BusinessStreamMessageVo 经 normalizer 校验后拆出；
    与 Token/ToolCall 等并列区分类型；是否推 SSE / 落库只看 persist、push_sse。
    """

    persist: bool  # 是否落库（role=business，content=data JSON）
    push_sse: bool  # 是否推前端（统一 event: business）
    data: Any  # 业务载荷；展示含义由前端按结构自行识别
