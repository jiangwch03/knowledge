"""
将 query_crawl_task / Planning 终稿中的业务上下文同步进 Agent state。

目的：
- Supervisor 查任务后写入 target_url / crawl_config / failed_*，下次 task 委派可拷贝给 Planning
- Planning 结束时从终稿 JSON 提取 crawl_config 写回，开爬前改方案不再冷启动断档
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from knowledge_common.utils.log_util import logger
from knowledge_content.agents.tools.crawl_task_query import query_crawl_task
from knowledge_content.agents.utils.strategy_config_util import extract_strategy_config

_URL_RE = re.compile(r'https?://[^\s\]\'"<>，,；;]+')


def extract_urls_from_text(text: str | None) -> list[str]:
    """从失败说明等文本中提取 URL（去重保序）"""
    if not text:
        return []
    seen: set[str] = set()
    urls: list[str] = []
    for match in _URL_RE.findall(text):
        url = match.rstrip(').]')
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def build_state_updates_from_query_payload(payload: dict) -> dict[str, Any]:
    """
    从 query_crawl_task JSON 构造可写入 state 的字段。

    - 查到任务（含 found / accessible 成功路径）：写入 target_url / task_id / crawl_config 等
    - 仅防重复未命中：至少写入请求的 target_url
    """
    updates: dict[str, Any] = {}
    if not isinstance(payload, dict) or not payload.get('success'):
        return updates

    target_url = (payload.get('target_url') or '').strip()
    if target_url:
        updates['target_url'] = target_url

    # 未命中任务：只记住 URL，不清空旧 crawl_config
    if payload.get('found') is False and 'task_id' not in payload:
        return updates

    task_id = payload.get('task_id')
    if isinstance(task_id, int):
        updates['task_id'] = task_id

    crawl_config = payload.get('crawl_config')
    if isinstance(crawl_config, dict) and crawl_config:
        updates['crawl_config'] = crawl_config

    error_message = payload.get('error_message')
    if isinstance(error_message, str) and error_message.strip():
        updates['failed_reason'] = error_message.strip()
        failed_urls = extract_urls_from_text(error_message)
        if failed_urls:
            updates['failed_urls'] = failed_urls

    # 结构化失败明细优先：URL 列表更准，失败说明拼上各页 error_message
    details = payload.get('failed_url_details')
    if isinstance(details, list) and details:
        detail_urls: list[str] = []
        detail_lines: list[str] = []
        for item in details:
            if not isinstance(item, dict):
                continue
            url = (item.get('url') or '').strip()
            if not url:
                continue
            if url not in detail_urls:
                detail_urls.append(url)
            code = item.get('error_code') or 'N/A'
            msg = (item.get('error_message') or '').strip() or 'N/A'
            detail_lines.append(f'{url} [{code}] {msg}')
        if detail_urls:
            updates['failed_urls'] = detail_urls
        if detail_lines:
            updates['failed_reason'] = '; '.join(detail_lines)

    return updates


def _tool_message_from_result(result: ToolMessage | Command[Any]) -> ToolMessage | None:
    if isinstance(result, ToolMessage):
        return result
    if isinstance(result, Command):
        update = result.update or {}
        messages = update.get('messages') or []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage):
                return msg
    return None


def _merge_command_with_updates(
    result: ToolMessage | Command[Any],
    updates: dict[str, Any],
) -> ToolMessage | Command[Any]:
    if not updates:
        return result
    if isinstance(result, ToolMessage):
        return Command(update={**updates, 'messages': [result]})
        if isinstance(result, Command):
            prev = dict(result.update or {})
            prev_messages = prev.pop('messages', None)
            merged = {**prev, **updates}
            if prev_messages is not None:
                merged['messages'] = prev_messages
            kwargs: dict[str, Any] = {'update': merged}
            if result.goto not in (None, (), []):
                kwargs['goto'] = result.goto
            if result.resume is not None:
                kwargs['resume'] = result.resume
            if result.graph is not None:
                kwargs['graph'] = result.graph
            return Command(**kwargs)
    return result


class CrawlerStateSyncMiddleware(AgentMiddleware):
    """
    Supervisor：拦截 query_crawl_task，把详情写入 state。
    Planning：agent 结束后从终稿提取 crawl_config 写回。
    """

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        result = await handler(request)
        tool_name = (request.tool_call or {}).get('name', '')
        if tool_name != query_crawl_task.name:
            return result

        tool_msg = _tool_message_from_result(result)
        if tool_msg is None:
            return result

        content = tool_msg.content
        if not isinstance(content, str) or not content.strip():
            return result

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            logger.warning('[CrawlerStateSync] query_crawl_task 返回非 JSON，跳过 state 同步')
            return result

        updates = build_state_updates_from_query_payload(payload)
        if not updates:
            return result

        logger.info(
            '[CrawlerStateSync] 同步 query 结果到 state: keys={}',
            sorted(updates.keys()),
        )
        return _merge_command_with_updates(result, updates)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        result = handler(request)
        tool_name = (request.tool_call or {}).get('name', '')
        if tool_name != query_crawl_task.name:
            return result

        tool_msg = _tool_message_from_result(result)
        if tool_msg is None or not isinstance(tool_msg.content, str):
            return result
        try:
            payload = json.loads(tool_msg.content)
        except json.JSONDecodeError:
            return result
        updates = build_state_updates_from_query_payload(payload)
        return _merge_command_with_updates(result, updates)

    async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self._extract_crawl_config_update(state)

    def after_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return self._extract_crawl_config_update(state)

    def _extract_crawl_config_update(self, state: Any) -> dict[str, Any] | None:
        messages = state.get('messages') if isinstance(state, dict) else None
        if not messages:
            return None

        for msg in reversed(messages):
            if not isinstance(msg, AIMessage):
                continue
            if getattr(msg, 'tool_calls', None):
                continue
            content = msg.content if isinstance(msg.content, str) else str(msg.content or '')
            config = extract_strategy_config(content)
            if config:
                logger.info(
                    '[CrawlerStateSync] Planning 终稿回流 crawl_config: keys={}',
                    sorted(config.keys()),
                )
                return {'crawl_config': config}
            break
        return None


crawler_state_sync_middleware = CrawlerStateSyncMiddleware()
