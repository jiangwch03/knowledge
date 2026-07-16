"""Planning 子图专用状态"""

from knowledge_common.agent.state.react import ReactBaseState
from knowledge_content.agents.states.crawler_agent_state import CrawlerAgentState


class PlanningState(ReactBaseState, CrawlerAgentState):
    """
    Planning 子图状态

    ReAct：探站 → 生成 strategy JSON → trial 验证。
    业务上下文字段（target_url / crawl_config / failed_*）继承自 CrawlerAgentState，
    由 Supervisor state 经 task 拷贝注入；终稿 crawl_config 经 middleware 写回。
    """
