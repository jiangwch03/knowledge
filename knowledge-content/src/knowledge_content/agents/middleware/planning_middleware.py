"""Planning create_agent middleware：动态 prompt + 按 context 换模型"""

from __future__ import annotations

import json
import re

from langchain.agents.middleware import ModelRequest, dynamic_prompt

from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.exceptions.exception import ServiceException


def _format_prompt_value(value: object, default: str = '用户未提供') -> str:
    """将 state 值转为可读字符串，用于替换 prompt 占位符。"""
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    return text if text else default


def _build_labeled_input(label: str, value: object) -> str:
    """构造 Planning 输入行：值为空则不注入该行。"""
    formatted = _format_prompt_value(value, default='')
    return f'{label}：{formatted}' if formatted else ''


def _render_planning_system_prompt(state: dict) -> str:
    system_prompt = prompt_config.get_system_prompt('crawler.planning')
    if not system_prompt:
        raise ServiceException('prompt_config.get_system_prompt("crawler.planning") 为空，异常终止')

    replacements = {
        '{target_url_input}': _build_labeled_input('目标 URL', state.get('target_url')),
        '{failed_urls_input}': _build_labeled_input('失败 URL 列表', state.get('failed_urls')),
        '{failed_reason_input}': _build_labeled_input('失败说明', state.get('failed_reason')),
        '{crawl_config_input}': _build_labeled_input('爬取参数配置', state.get('crawl_config')),
    }
    # 目标 URL / crawl_config / failed_* 可由 Supervisor state 经 task 拷贝注入
    for key, val in replacements.items():
        system_prompt = system_prompt.replace(key, str(val))
    # 清理空注入留下的空列表项（"- "）
    system_prompt = re.sub(r'^\s*-\s*$\n?', '', system_prompt, flags=re.MULTILINE)
    system_prompt = re.sub(r'\n{3,}', '\n\n', system_prompt)
    return system_prompt


@dynamic_prompt
def planning_system_prompt(request: ModelRequest) -> str:
    """按 PlanningState 动态渲染 system prompt（target_url/failed_urls/failed_reason/crawl_config）"""
    return _render_planning_system_prompt(request.state)


# 模型切换见 agents.middleware.crawler_model_middleware
