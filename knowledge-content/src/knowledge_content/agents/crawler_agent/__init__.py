"""网页爬取 Agent 父图入口（延迟导入，避免包加载时拉起全量依赖链）"""

from typing import Any

__all__ = ['get_root_graph']


def __getattr__(name: str) -> Any:
    if name == 'get_root_graph':
        from knowledge_content.agents.crawler_agent.graph import get_root_graph

        return get_root_graph
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
