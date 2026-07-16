"""
astream 归一化生成器（框架层，零业务耦合）

驱动 LangGraph astream，把原始事件流「拆包 + 分类」成归一化事件，供各业务
Agent 服务统一消费。业务层只需 `async for ev in normalize_astream(...)` 然后
按事件类型决定「落库 / SSE / 聚合」等具体处理。

本模块的边界严格限定在：
  - astream 的调用姿势（双 stream_mode + subgraphs + version）
  - 由 namespaces 判定父图 / 子图来源
  - 兼容 deepagents 的 Overwrite(value=[...]) 提取消息
  - 按 python 消息类型分类为归一化事件

不含任何落库、SSE、HITL、脱敏、子图聚合策略等业务逻辑；异常也不吞，交由调用方
兜底（业务方通常需要把异常翻译成自己的错误协议）。
"""

from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, Overwrite

from knowledge_common.agent.stream.events import (
    SOURCE_SUBAGENT,
    SOURCE_SUPERVISOR,
    AITextEvent,
    HumanMessageEvent,
    NormalizedEvent,
    PlainMessageEvent,
    SystemMessageEvent,
    TokenEvent,
    ToolCallEvent,
    ToolResultEvent,
)

# ── astream 的两种流式来源（并行、非互斥）──
# 同一 LLM 节点执行时，两种事件会交错产出：
#   messages — 执行过程中逐 token 推送（AIMessageChunk），供打字机
#   updates  — 节点执行完毕时吐出该节点的状态增量（含完整 AIMessage），供落库/工具卡片
STREAM_MODE_MESSAGES = 'messages'
STREAM_MODE_UPDATES = 'updates'


async def normalize_astream(
    compiled: CompiledStateGraph,
    *,
    config: dict,
    context: dict,
    input_or_resume: Command | dict,
    skip_update_nodes: frozenset[str] = frozenset(),
) -> AsyncIterator[NormalizedEvent]:
    """
    驱动 astream 并逐个产出归一化事件。

    :param compiled: 已编译的 LangGraph 图
    :param config: astream 的 configurable 配置（含 thread_id 等）
    :param context: 注入图运行期的上下文（如身份信息，已 model_dump）
    :param input_or_resume: 本轮输入（dict）或中断恢复指令（Command）
    :param skip_update_nodes: 需要跳过 update 的节点名集合（如仅修补历史的中间件节点），
                              避免旧消息重放；跳过仅影响事件产出，不影响图 state
    :return: 归一化事件异步生成器
    """
    async for item in compiled.astream(
        input=input_or_resume,
        config=config,
        context=context,
        stream_mode=[STREAM_MODE_MESSAGES, STREAM_MODE_UPDATES],
        subgraphs=True,
        version='v2',
    ):
        source, agent_ns = _resolve_source(item.get('ns') or ()) # 判定事件来自父图还是子图
        mode = item.get('type') # messages 或 updates
        data = item.get('data') # 消息数据
        if mode == STREAM_MODE_MESSAGES: # 处理 messages 模式
            token = _normalize_token(data, source, agent_ns) # 归一化为 TokenEvent
            if token is not None:
                yield token # 产出 TokenEvent
        elif mode == STREAM_MODE_UPDATES: # 处理 updates 模式
            for event in _normalize_updates(data, source, agent_ns, skip_update_nodes): # 归一化为业务语义事件
                yield event # 产出业务语义事件


def _resolve_source(namespaces: tuple) -> tuple[str, str | None]:
    """
    由 astream 的 namespaces 判定事件来自父图还是子图。

    - namespaces 为空 ()  → 父图（supervisor），agent_ns=None
    - namespaces 非空      → 子图（如 planning），拼接串作为该子图框的稳定分组 id
    """
    if not namespaces:
        return SOURCE_SUPERVISOR, None
    return SOURCE_SUBAGENT, '|'.join(str(n) for n in namespaces)


def _resolve_message_text(msg: AIMessage | AIMessageChunk) -> str:
    """从消息对象提取纯文本，兼容 LangChain 新旧 .text API（property / method）。"""
    if not msg.content:
        return ''
    text = msg.text
    if isinstance(text, str):
        return text
    if callable(text):
        return text()  # LangChain <1.0：.text 仍为方法
    return str(msg.content)


def _extract_chunk_text(chunk: AIMessageChunk) -> str:
    """从 AIMessageChunk 提取纯文本（兼容 content blocks 列表形态）。"""
    return _resolve_message_text(chunk)


def _normalize_token(data, source: str, agent_ns: str | None) -> TokenEvent | None:
    """messages 模式：只保留有内容的 AIMessageChunk，归一化为 TokenEvent。"""
    chunk, _metadata = data
    if not isinstance(chunk, AIMessageChunk):
        return None
    text = _extract_chunk_text(chunk)
    if not text:
        return None
    return TokenEvent(source=source, agent_ns=agent_ns, content=text)


def _normalize_updates(
    data: dict | None,
    source: str,
    agent_ns: str | None,
    skip_update_nodes: frozenset[str],
) -> list[NormalizedEvent]:
    """
    updates 模式：遍历各节点 update，把每条消息拆解成业务语义事件。

    :param data: 单个 updates 事件的 payload，形如 {节点名: 该节点的 update}；可能为 None
    :param source: 事件来源（SOURCE_SUPERVISOR / SOURCE_SUBAGENT），由 namespaces 判定
    :param agent_ns: 子图分组 id；父图为 None
    :param skip_update_nodes: 需跳过的节点名集合（如仅修补历史的中间件节点），命中则不产出事件
    :return: 该 update 拆解出的业务语义事件列表（一条消息可能拆成多个事件）
    """
    events: list[NormalizedEvent] = []
    for node_name, update in (data or {}).items():
        if node_name in skip_update_nodes: # 跳过需要跳过的节点名集合
            continue
        for msg in _extract_messages(update):
            events.extend(_decompose_message(msg, source, agent_ns)) # 把消息拆解成业务语义事件
    return events # 返回该 update 拆解出的业务语义事件列表（一条消息可能拆成多个事件）


def _extract_messages(update) -> list:
    """
    从单个节点的 update 取出消息列表（兼容 deepagents 的 Overwrite(value=[...])）。

    LangGraph 里 update 有三种常见形状（都归一成 list[BaseMessage] 返回）：

      1) 标准 dict（最常见）——节点返回 {'messages': [...]} 形式的状态增量：
         {
             'messages': [AIMessage(...), ToolMessage(...)],
             'react_round': 3,          # 可能还带其它业务字段
         }

      2) 直接是消息列表——少数节点直接把 update 给成一个 list：
         [AIMessage(...), ToolMessage(...)]

      3) deepagents 的 Overwrite 包裹——子图用它做「整体覆盖」而非追加，
         真正的消息在 .value 里：
         Overwrite(value=[AIMessage(...), ToolMessage(...)])

    :param update: 上述三种形状之一（也可能为 None / 空）
    :return: 归一化后的消息列表，恒为 list（无消息时为空 list）
    """
    # 形状 1 取 'messages' 键；形状 2/3 update 本身就是数据（list 或 Overwrite）
    raw = update.get('messages', []) if isinstance(update, dict) else update
    # 形状 3：Overwrite 的真实数据在 .value 里
    if isinstance(raw, Overwrite):
        return list(raw.value or [])
    # 形状 2（或形状 1 取出的 list）：兜底 None 后转 list
    return list(raw or [])


def _decompose_message(msg, source: str, agent_ns: str | None) -> list[NormalizedEvent]:
    """
    把一条 langchain 消息拆解成业务语义事件（不含任何业务判断）。

    - AIMessage：有文本 → AITextEvent；每个 tool_call → ToolCallEvent
    - ToolMessage：ToolResultEvent
    - SystemMessage / HumanMessage：SystemMessageEvent / HumanMessageEvent
    - 其它：PlainMessageEvent（兜底，保留原始 message）
    """
    if isinstance(msg, AIMessage):
        return _decompose_ai_message(msg, source, agent_ns)
    if isinstance(msg, ToolMessage):
        return [ToolResultEvent(
            source=source,
            agent_ns=agent_ns,
            tool_call_id=getattr(msg, 'tool_call_id', '') or '',
            tool_name=getattr(msg, 'name', '') or '',
            content=msg.content or '',
        )]
    if isinstance(msg, SystemMessage):
        return [SystemMessageEvent(source=source, agent_ns=agent_ns, content=msg.content or '')]
    if isinstance(msg, HumanMessage):
        return [HumanMessageEvent(source=source, agent_ns=agent_ns, content=msg.content or '')]
    return [PlainMessageEvent(source=source, agent_ns=agent_ns, message=msg)]


def _extract_ai_text(msg: AIMessage) -> str:
    """
    从 AIMessage 提取可落库的纯文本。

  LangChain 合并 AIMessage 后（尤其带 tool_calls 时），content / content blocks
  尾部常附带空白；落库前 rstrip，避免前端气泡被撑出大片空白。
    """
    return _resolve_message_text(msg).rstrip()


def _decompose_ai_message(msg: AIMessage, source: str, agent_ns: str | None) -> list[NormalizedEvent]:
    """拆解 AIMessage：先文本，后工具调用。"""
    events: list[NormalizedEvent] = []
    text = _extract_ai_text(msg)
    if text:
        events.append(AITextEvent(source=source, agent_ns=agent_ns, content=text))
    for tool_call in msg.tool_calls or []:
        events.append(ToolCallEvent(
            source=source,
            agent_ns=agent_ns,
            tool_call_id=tool_call.get('id', '') or '',
            tool_name=tool_call.get('name', '') or '',
            tool_args=tool_call.get('args', {}) or {},
        ))
    return events
