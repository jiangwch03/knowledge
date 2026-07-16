"""Planning 子图入口（延迟导入）"""

from typing import Any

__all__ = ['get_planning_subgraph']


def __getattr__(name: str) -> Any:
    if name == 'get_planning_subgraph':
        from knowledge_content.agents.crawler_agent.workers.planning.graph import get_planning_subgraph

        return get_planning_subgraph
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
