"""
deepagents Supervisor 工厂

使用 create_deep_agent + CompiledSubAgent(planning) 构建 Supervisor。
Planning 子图通过框架内置 task 工具委派，不再使用手写 task_planning 工具。

说明：该模块只负责「Agent 执行内核」。
对外面客能力（SSE 事件协议、消息落库审计、resume 参数映射）由
CrawlerAgentService 统一封装，不直接暴露 deepagents 原生接口。

ReAct 循环退出机制（create_deep_agent → langchain create_agent）：
  1. 正常退出：model 产出的 AIMessage 不含 tool_calls → 路由到 END，本轮 Supervisor 结束。
     （有 tool_calls → 进 tools 节点执行 → 再回 model，如此往复）
  2. 安全阀：create_deep_agent 默认 with_config(recursion_limit=1000)，
     图 superstep 触顶抛 GraphRecursionError，不是业务「最大轮次」语义。
  3. Planning 子 Agent 同样使用 create_agent + ModelCallLimitMiddleware(run_limit=…)。
  4. 写操作确认走 HITL（interrupt_on）：LLM 发出 crawl_execute / apply_scope_change
     后、执行前必拦。策略是否执行由对话约定（用户回复「爬取」等），不再走父图 interrupt_gate。

deepagents API 限制与适配细节见 docs/rag功能流程说明/缺陷修复优化/deepagents集成缺陷与适配说明.md
"""

from __future__ import annotations

import json
import threading

from deepagents import CompiledSubAgent, create_deep_agent
import deepagents.graph as _deepagents_graph
from langchain.agents import create_agent as _langchain_create_agent
from langchain.agents.middleware import InterruptOnConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from knowledge_common.agent.schema.context import AgentIdentityContext
from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.crawler_agent.workers.planning.graph import get_planning_subgraph
from knowledge_content.agents.middleware.crawler_model_middleware import crawler_model_middleware
from knowledge_content.agents.middleware.crawler_state_sync_middleware import (
    crawler_state_sync_middleware,
)
from knowledge_content.agents.states.crawler_supervisor_state import SupervisorState
from knowledge_content.agents.tools import CRAWL_AGENT_DEEP_SUPERVISOR_TOOLS
from knowledge_content.agents.tools.apply_scope_change import apply_scope_change
from knowledge_content.agents.tools.crawl_merge_results import merge_crawl_results, persist_crawl_results
from knowledge_content.agents.tools.crawl_execute import crawl_execute
from knowledge_content.agents.tools.crawl_retry import crawl_retry
from knowledge_content.agents.tools.crawl_task_delete import delete_crawl_task
from knowledge_content.agents.tools.crawl_task_pause import pause_crawl_task
from knowledge_content.agents.tools.crawl_task_resume import resume_crawl_task
from knowledge_content.agents.utils.llm_util import get_base_chat_model
from knowledge_common.agent.memory.short_memory.checkpointer import Checkpointer

_deep_supervisor_graph: CompiledStateGraph | None = None
_deep_supervisor_lock: threading.Lock = threading.Lock()


def _format_crawl_config_summary(crawl_config) -> str:
    """HITL 摘要：crawl_config 已是 JSON 字符串时不再 dumps，避免双重转义。"""
    if crawl_config is None:
        return '{}'
    if isinstance(crawl_config, str):
        return crawl_config.strip()[:800] or '{}'
    return json.dumps(crawl_config, ensure_ascii=False)[:800]


def _tool_hitl_description(tool_call, _state, _runtime) -> str:
    """HITL 弹窗 description：按工具名拼确认提示（展示给前端 user_choice）"""
    name = tool_call.get('name', '')
    args = tool_call.get('args', {})
    config_summary = _format_crawl_config_summary(args.get('crawl_config'))
    target_url = (args.get('target_url') or '').strip() or '（未传入）'

    match name:
        case _ if name == crawl_execute.name: # 执行工具
            return (
                '确认提交正式爬取任务？\n'
                f'目标 URL: {target_url}\n'
                f'配置摘要: {config_summary}'
            )
        case _ if name == apply_scope_change.name: # 应用新的爬取范围
            remove = args.get('urls_to_remove') or []
            scope_url = (args.get('target_url') or '').strip() or '（未传入，沿用任务原 URL）'
            return (
                '确认应用新的爬取范围？\n'
                f'目标 URL: {scope_url}\n'
                f'待删除 URL 数: {len(remove)}\n'
                f'配置摘要: {config_summary}'
            )
        case _ if name == pause_crawl_task.name: # 暂停爬取任务
            return (
                '确认暂停爬取任务？\n'
                f"任务 ID: {args.get('task_id', '未知')}"
            )
        case _ if name == resume_crawl_task.name: # 恢复爬取任务
            return (
                '确认恢复爬取任务？\n'
                f"任务 ID: {args.get('task_id', '未知')}"
            )
        case _ if name == delete_crawl_task.name: # 删除爬取任务
            return (
                '确认删除爬取任务？（软删除）\n'
                f"任务 ID: {args.get('task_id', '未知')}\n"
                '删除后任务将不再展示。'
            )
        case _ if name in (persist_crawl_results.name, merge_crawl_results.name, 'merge_crawl_results'):
            return (
                '确认提交入库已爬取结果？\n'
                f"任务 ID: {args.get('task_id', '未知')}\n"
                '将放弃失败 URL，并把已成功页面投入文档落库队列（异步落库，'
                '提交成功不等于已写入知识库）。'
            )
        case _ if name == crawl_retry.name: # 重试爬取任务  
            retry_url = (args.get('target_url') or '').strip() or '（未传入，沿用任务原 URL）'
            return (
                '确认重试爬取任务？\n'
                f"任务 ID: {args.get('task_id', '未知')}\n"
                f'目标 URL: {retry_url}\n'
                f'配置摘要: {config_summary}'
            )
        case _: # 其他工具
            return f'确认执行工具 {name}？\n参数: {json.dumps(args, ensure_ascii=False)[:500]}'


# 危险写操作：LLM 发出对应 tool_call 后、执行前暂停，等人 approve/reject
_hitl_config = InterruptOnConfig(
    allowed_decisions=['approve', 'reject'],
    description=_tool_hitl_description,
)
# 创建 agent 时，将 context_schema 映射到 state_schema
def _create_agent_with_state_schema(*args, **kwargs):
        context_schema = kwargs.pop('context_schema', None)
        if context_schema is not None:
            kwargs['state_schema'] = context_schema
        kwargs['context_schema'] = AgentIdentityContext
        return _langchain_create_agent(*args, **kwargs)

async def build_deep_supervisor_graph() -> CompiledStateGraph:
    """
    构建 deepagents Supervisor（CompiledStateGraph）
    """
    default_model = await get_base_chat_model(None)
    system_prompt = prompt_config.get_system_prompt('crawler.supervisor')

    planning_agent = CompiledSubAgent(
        name='planning_agent',
        description='分析网站结构、生成/调整 crawl4ai 爬取策略并 trial 验证。',
        runnable=await get_planning_subgraph(),
    )

    interrupt_on = {
        crawl_execute.name: _hitl_config,
        apply_scope_change.name: _hitl_config,
        pause_crawl_task.name: _hitl_config,
        resume_crawl_task.name: _hitl_config,
        delete_crawl_task.name: _hitl_config,
        persist_crawl_results.name: _hitl_config,
        crawl_retry.name: _hitl_config,
    }

    # deepagents 仅暴露 context_schema 参数。若不显式映射到 state_schema，
    # task 工具无法从 runtime.state 拷贝业务字段。
    # 这里保持业务 state 与 runtime context 分离：
    #   - state_schema: SupervisorState（跨轮次持久化；目标 URL 由工具入参传入）
    #   - context_schema: AgentIdentityContext（单次 invoke 上下文，如 model_id/user_id）
    _orig_create_agent = _deepagents_graph.create_agent
    try:
        # 覆盖原始 create_agent 函数
        _deepagents_graph.create_agent = _create_agent_with_state_schema
        # 获取 checkpointer
        _checkpointer: Checkpointer = await Checkpointer.get_checkpointer()
        # 创建 deepagents Supervisor
        graph = create_deep_agent(
            model=default_model,
            tools=CRAWL_AGENT_DEEP_SUPERVISOR_TOOLS,
            system_prompt=system_prompt,
            middleware=[
                crawler_model_middleware,
                crawler_state_sync_middleware,
            ],
            subagents=[planning_agent],
            context_schema=SupervisorState,
            checkpointer=_checkpointer,
            interrupt_on=interrupt_on,
            name='crawler_supervisor',
        )
    finally:
        # 恢复原始 create_agent 函数
        _deepagents_graph.create_agent = _orig_create_agent

    logger.info('[CrawlerAgent] deepagents Supervisor 构建完成 (planning_agent=CompiledSubAgent)')
    return graph


async def get_deep_supervisor_graph() -> CompiledStateGraph:
    """deepagents Supervisor 单例"""
    global _deep_supervisor_graph
    if _deep_supervisor_graph is None:
        with _deep_supervisor_lock:
            if _deep_supervisor_graph is None:
                _deep_supervisor_graph = await build_deep_supervisor_graph()
    return _deep_supervisor_graph
