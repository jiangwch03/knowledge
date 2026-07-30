"""
ReAct 循环触顶时注入合成 ToolMessage 的 LangGraph 节点

当 ReAct 循环达到最大轮次限制，但 LLM 最后一条消息仍有未执行的 tool_calls 时，
为每个 tool_call 注入一条合成 ToolMessage 说明调用已跳过，
使消息历史保持 tool_call ↔ tool_result 配对完整，避免下游推理异常。

该节点与业务无关，可被任意 ReAct Agent 图复用。
最大轮次由业务方通过 make_max_round_inject_node(max_rounds) 指定。
"""

from collections.abc import Awaitable, Callable

from langchain_core.messages import ToolMessage

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger

# LangGraph 条件边路由名称：当达到最大 ReAct 轮次且有未执行 tool_calls 时使用
MAX_ROUND_INJECT = 'tool_inject'


def make_max_round_inject_node(max_rounds: int) -> Callable[[dict], Awaitable[dict]]:
    """
    构造「达到最大 ReAct 轮次时注入合成 ToolMessage」的节点

    :param max_rounds: 业务方配置的最大 ReAct 轮次，仅用于提示文案
    :return: 可注册到 StateGraph 的异步节点函数
    """

    async def max_round_inject_node(state: dict) -> dict:
        """
        达到最大 ReAct 轮次时，为未执行的工具调用注入合成 ToolMessage

        ReAct 循环触顶时，LLM 最后一条消息可能仍有 tool_calls。
        直接跳过会使消息历史中 tool_call ↔ tool_result 配对缺失，
        影响 LLM 下游推理的一致性。本节点为每个未执行的 tool_call 生成一条
        合成 ToolMessage，说明已跳过该调用，使消息序列保持完整。

        :param state: Agent 状态字典，需要包含 messages 列表
        :return: 合成 ToolMessage 列表（会被 LangGraph 合并到 state.messages）
        """
        logger.info('[Agent] max_round_inject_node: 注入合成 ToolMessage（已达最大轮次 {}）', max_rounds)

        if not state.get('messages'):
            raise ServiceException('max_round_inject_node: state["messages"] 为空，异常终止')

        last_message = state['messages'][-1]

        tool_messages = []
        for tool_call in last_message.tool_calls:
            tool_call_id = tool_call['id'] if isinstance(tool_call, dict) else tool_call.id
            tool_name = tool_call['name'] if isinstance(tool_call, dict) else tool_call.name
            tool_messages.append(ToolMessage(
                content=(
                    f'【系统强制终止】已达到最大分析轮次限制（{max_rounds}轮），'
                    f'工具「{tool_name}」未执行且禁止再次调用任何工具。'
                    f'你必须立即停止工具调用，仅根据当前已有分析结果直接给出最终总结答案，'
                    f'不得再发起 tool_calls / function call。'
                ),
                tool_call_id=tool_call_id,
                name=tool_name,
            ))

        return {'messages': tool_messages}

    return max_round_inject_node
