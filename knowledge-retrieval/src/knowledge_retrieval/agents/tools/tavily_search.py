"""Tavily 联网搜索 Tool：Key 来自 sys_config rag.tavily.api_key；空则友好降级。"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from knowledge_common.redis import RedisConnection
from knowledge_common.service.config_service import ConfigService
from knowledge_common.utils.log_util import logger

TAVILY_CONFIG_KEY = 'rag.tavily.api_key'
_PLACEHOLDERS = {'', 'YOUR_TAVILY_API_KEY', 'placeholder', 'changeme', 'todo'}


class TavilySearchInput(BaseModel):
    query: str = Field(..., description='联网搜索查询')
    max_results: int = Field(default=3, ge=1, le=5, description='返回条数，默认 3')


async def _load_tavily_api_key() -> str | None:
    # ConfigService 缓存挂在 app redis；无 app 上下文时直接视为未配置
    try:
        from knowledge_common.common.context import RequestContext

        request = RequestContext.get_current_request()
        redis = request.app.state.redis
    except Exception:
        try:
            redis = await RedisConnection.create_redis_pool(log_enabled=False)
        except Exception:
            return None
    value = await ConfigService.query_config_list_from_cache_services(redis, TAVILY_CONFIG_KEY)
    if value is None:
        return None
    key = str(value).strip()
    if key.lower() in _PLACEHOLDERS:
        return None
    return key


async def _tavily_search(query: str, max_results: int = 3) -> str:
    api_key = await _load_tavily_api_key()
    if not api_key:
        return json.dumps(
            {
                'ok': False,
                'source_type': 'web',
                'message': 'Tavily API Key 未配置（sys_config: rag.tavily.api_key），已跳过联网搜索',
                'results': [],
            },
            ensure_ascii=False,
        )

    try:
        from langchain_community.tools.tavily_search import TavilySearchResults

        tool = TavilySearchResults(max_results=max_results, tavily_api_key=api_key)
        raw = await tool.ainvoke({'query': query})
    except Exception as exc:
        logger.warning('[Tavily] 搜索失败，降级: {}', exc)
        return json.dumps(
            {
                'ok': False,
                'source_type': 'web',
                'message': f'联网搜索暂时不可用: {type(exc).__name__}',
                'results': [],
            },
            ensure_ascii=False,
        )

    results: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                results.append(
                    {
                        'title': item.get('title'),
                        'url': item.get('url'),
                        'content': item.get('content') or item.get('snippet'),
                        'source_type': 'web',
                    }
                )
    return json.dumps({'ok': True, 'source_type': 'web', 'results': results}, ensure_ascii=False)


tavily_search = StructuredTool.from_function(
    coroutine=_tavily_search,
    name='tavily_search',
    description=(
        '联网搜索补充实时/库外信息。返回 JSON，其中 source_type=web，'
        '不可与知识库 citation 混淆。Key 未配置时返回友好失败，不中断会话。'
    ),
    args_schema=TavilySearchInput,
)
