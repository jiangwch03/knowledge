"""
正式写操作（提交 / 重试 / 改范围）共用门禁。

统一处理：解析 crawl_config、解析身份、解析生效 URL、起点范围校验、试爬凭证校验。
工具层仍保持三个入口，仅共享校验，不合并业务语义。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from knowledge_common.agent.schema.context import (
    AgentIdentityContextVo,
    get_agent_identity_from_tool_runtime,
)
from knowledge_common.exceptions.exception import format_exception_message
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.filter_chain_util import evaluate_seed_scope
from knowledge_content.agents.utils.strategy_config_util import parse_tool_crawl_config
from knowledge_content.agents.utils.trial_verified_gate import (
    failed_samples_not_verified_summary,
    is_any_trial_verified,
    is_trial_verified,
    trial_not_verified_summary,
)


@dataclass(frozen=True)
class CrawlSubmitPrepared:
    """门禁通过后的写操作入参。"""

    identity: AgentIdentityContextVo
    target_url: str
    crawl_config: dict


def _reject_json(
    *,
    summary: str,
    task_id: int | None = None,
    url: str = '',
    status: str = 'failed',
    extra: dict | None = None,
) -> str:
    """统一失败 JSON；同时带 summary / message，兼容各工具消费习惯。"""
    payload: dict[str, Any] = {
        'success': False,
        'task_id': task_id,
        'status': status,
        'url': url,
        'summary': summary,
        'message': summary,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False)


def parse_submit_crawl_config(
    crawl_config_arg: Any,
    *,
    log_tag: str,
    task_id: int | None = None,
    url: str = '',
    require_nonempty: bool = True,
) -> dict | str:
    """
    解析写操作的 crawl_config。

    :return: 成功返回 dict；失败返回可直接给工具返回的 JSON 字符串
    """
    try:
        parsed = parse_tool_crawl_config(crawl_config_arg)
    except ValueError as e:
        logger.exception('[{}] crawl_config 解析失败: {}', log_tag, e)
        return _reject_json(
            summary=f'爬取配置解析失败: {e}',
            task_id=task_id,
            url=url,
        )

    if require_nonempty and not parsed:
        logger.error('[{}] 缺少爬取配置', log_tag)
        return _reject_json(
            summary='缺少爬取配置',
            task_id=task_id,
            url=url,
        )
    return parsed or {}


def resolve_submit_identity(
    runtime: Any,
    *,
    log_tag: str,
    task_id: int | None = None,
    url: str = '',
) -> AgentIdentityContextVo | str:
    """解析工具 runtime 身份；失败返回 JSON 字符串。"""
    try:
        return get_agent_identity_from_tool_runtime(runtime)
    except Exception as e:
        err = format_exception_message(e)
        logger.exception('[{}] 身份上下文非法: {}', log_tag, err)
        return _reject_json(
            summary=f'系统错误：身份上下文非法: {err}',
            task_id=task_id,
            url=url,
        )


def resolve_effective_target_url(
    target_url: str | None,
    fallback_url: str | None = None,
) -> str:
    """优先使用显式传入 URL，否则回落到任务原 URL。"""
    return (target_url or '').strip() or (fallback_url or '').strip()


async def check_seed_and_trial_gates(
    *,
    session_id: int,
    target_url: str,
    crawl_config: dict,
    log_tag: str,
    action_hint: str,
    task_id: int | None = None,
    require_trial_urls: list[str] | None = None,
    also_require_target_trial: bool = True,
) -> str | None:
    """
    起点范围 + 试爬凭证硬门禁。

    :param action_hint: 用户提示里的动作文案，如「再提交」「再重试」「再应用新范围」
    :param require_trial_urls: 额外必须试爬成功的 URL（失败修复样本）；None 表示不额外校验
    :param also_require_target_trial: 是否仍要求 target_url 本身有试爬凭证
    :return: 拒绝时返回 JSON 字符串；通过返回 None
    """
    scope = evaluate_seed_scope(target_url, crawl_config)
    if not scope['expansion_ok']:
        hint = '、'.join(scope['suggested_seed_urls'][:3]) if scope['suggested_seed_urls'] else ''
        detail = '；'.join(scope['suggestions']) or '起点与 include_patterns 不匹配'
        if hint:
            detail = f'{detail}。建议入口：{hint}'
        ask_user = (
            f'当前起点 {target_url} 几乎扩不进目标板块，正式爬只会落到极少页面。'
            f'请改用建议入口后{action_hint}：{hint or "板块入口 URL"}'
        )
        logger.warning(
            '[{}] 起点范围门禁拒绝: task_id={}, url={}, issues={}',
            log_tag, task_id, target_url, scope['issues'],
        )
        return _reject_json(
            summary=f'操作被拒绝：{detail}',
            task_id=task_id,
            url=target_url,
            extra={
                'expansion_ok': False,
                'seed_in_scope': scope['seed_in_scope'],
                'suggested_seed_urls': scope['suggested_seed_urls'],
                'issues': scope['issues'],
                'ask_user': ask_user,
                'needs_user_confirm_new_url': True,
            },
        )

    sample_urls = [u.strip() for u in (require_trial_urls or []) if (u or '').strip()]
    if sample_urls:
        # OR：本任务任一失败 URL 试通即可（第 1 个或第 99 个都行）
        if not await is_any_trial_verified(session_id, sample_urls, crawl_config):
            hint_urls = sample_urls[:3]
            summary = failed_samples_not_verified_summary(
                hint_urls, total_failed=len(sample_urls),
            )
            logger.warning(
                '[{}] 失败样本试爬凭证门禁拒绝(需任一失败URL): session_id={}, task_id={}, '
                'failed_count={}, hints={}',
                log_tag, session_id, task_id, len(sample_urls), hint_urls,
            )
            return _reject_json(
                summary=summary,
                task_id=task_id,
                url=target_url,
                extra={
                    'trial_verified': False,
                    'missing_failed_urls': hint_urls,
                    'failed_url_count': len(sample_urls),
                    'require_any_failed_url': True,
                },
            )

    if also_require_target_trial and not await is_trial_verified(
        session_id, target_url, crawl_config,
    ):
        summary = trial_not_verified_summary(target_url)
        logger.warning(
            '[{}] 试爬凭证门禁拒绝: session_id={}, task_id={}, url={}',
            log_tag, session_id, task_id, target_url,
        )
        return _reject_json(
            summary=summary,
            task_id=task_id,
            url=target_url,
            extra={'trial_verified': False},
        )
    return None


async def prepare_crawl_submit(
    *,
    runtime: Any,
    crawl_config_arg: Any,
    target_url: str | None,
    fallback_url: str | None = None,
    task_id: int | None = None,
    require_nonempty_config: bool = True,
    log_tag: str,
    action_hint: str,
    require_trial_urls: list[str] | None = None,
    also_require_target_trial: bool = True,
) -> CrawlSubmitPrepared | str:
    """
    写操作共用准备流程：解析配置 → 身份 → 生效 URL → 起点/试爬门禁。

    :param require_trial_urls: 失败修复时传入须验证的失败样本 URL
    :param also_require_target_trial: 有失败样本时可不强制入口页凭证（样本已证明配置）
    :return: 成功返回 CrawlSubmitPrepared；失败返回可直接作为工具响应的 JSON 字符串
    """
    url_hint = resolve_effective_target_url(target_url, fallback_url)

    parsed = parse_submit_crawl_config(
        crawl_config_arg,
        log_tag=log_tag,
        task_id=task_id,
        url=url_hint,
        require_nonempty=require_nonempty_config,
    )
    if isinstance(parsed, str):
        return parsed

    identity = resolve_submit_identity(
        runtime, log_tag=log_tag, task_id=task_id, url=url_hint,
    )
    if isinstance(identity, str):
        return identity

    effective_url = resolve_effective_target_url(target_url, fallback_url)
    if not effective_url:
        return _reject_json(
            summary='缺少目标 URL，请传入用户确认的入口网址',
            task_id=task_id,
        )

    rejected = await check_seed_and_trial_gates(
        session_id=identity.session_id,
        target_url=effective_url,
        crawl_config=parsed,
        log_tag=log_tag,
        action_hint=action_hint,
        task_id=task_id,
        require_trial_urls=require_trial_urls,
        also_require_target_trial=also_require_target_trial,
    )
    if rejected:
        return rejected

    return CrawlSubmitPrepared(
        identity=identity,
        target_url=effective_url,
        crawl_config=parsed,
    )
