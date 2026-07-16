"""
试爬成功硬门禁：正式提交的 (url, crawl_config) 必须先被 trial_crawl 验证通过。

试爬成功后按 session 写入 Redis；crawl_execute 校验同一指纹存在才允许建任务。
指纹忽略 strategy_summary 等元数据；crawl4ai 策略本体变更后必须重新试爬。
"""

from __future__ import annotations

from knowledge_common.redis import RedisClient, RedisKey
from knowledge_common.utils.fingerprint_util import FingerprintUtil
from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.strategy_config_util import sanitize_strategy_config

# 会话内试爬凭证有效期（秒）
_TRIAL_VERIFIED_TTL_SECONDS = 6 * 60 * 60

# 指纹额外剥离：不影响 crawl4ai 运行的文案/分类字段
_FINGERPRINT_EXTRA_META = frozenset({'site_type'})


def build_trial_fingerprint(url: str, crawl_config: dict | None) -> str:
    """
    生成 url + 策略本体的稳定指纹。

    :param url: 试爬 / 正式提交的起点 URL
    :param crawl_config: 原始策略配置（试爬限流前、正式提交同一份）
    :return: sha256 hex
    """
    cleaned = sanitize_strategy_config(crawl_config or {})
    cleaned = {k: v for k, v in cleaned.items() if k not in _FINGERPRINT_EXTRA_META}
    return FingerprintUtil.of({
        'url': (url or '').strip(),
        'config': cleaned,
    })


async def mark_trial_verified(session_id: int, url: str, crawl_config: dict | None) -> str:
    """
    记录本会话下该 (url, config) 已试爬成功。

    :return: 写入的指纹
    """
    fingerprint = build_trial_fingerprint(url, crawl_config)
    key = RedisKey.crawl_trial_verified_key(session_id, fingerprint)
    await RedisClient.set(
        key,
        {'url': (url or '').strip(), 'fingerprint': fingerprint},
        ex=_TRIAL_VERIFIED_TTL_SECONDS,
    )
    logger.info(
        '[TrialVerifiedGate] 已记录试爬凭证: session_id={}, url={}, fp={}',
        session_id, (url or '').strip(), fingerprint[:12],
    )
    return fingerprint


async def is_trial_verified(session_id: int, url: str, crawl_config: dict | None) -> bool:
    """本会话是否已对相同 url+策略本体试爬成功。"""
    fingerprint = build_trial_fingerprint(url, crawl_config)
    key = RedisKey.crawl_trial_verified_key(session_id, fingerprint)
    exists = await RedisClient.exists(key)
    return bool(exists)


async def is_any_trial_verified(
    session_id: int,
    urls: list[str],
    crawl_config: dict | None,
    *,
    chunk_size: int = 500,
) -> bool:
    """
    本会话是否已对 urls 中「任意一个」+ 相同策略试爬成功。

    批量 EXISTS，不按失败页数线性发 N 次往返；命中任一 chunk 即返回。
    """
    keys: list[str] = []
    for url in urls:
        cleaned = (url or '').strip()
        if not cleaned:
            continue
        fingerprint = build_trial_fingerprint(cleaned, crawl_config)
        keys.append(RedisKey.crawl_trial_verified_key(session_id, fingerprint))
    if not keys:
        return False

    size = max(1, chunk_size)
    for i in range(0, len(keys), size):
        chunk = keys[i:i + size]
        if await RedisClient.exists(*chunk) > 0:
            return True
    return False


def trial_not_verified_summary(url: str) -> str:
    """配置变更类工具（执行/重试/改范围）拒绝时的可读说明。"""
    return (
        f'操作被拒绝：目标地址 {url} 对应的爬取配置尚未在本会话试爬成功过。'
        f'请先用完全相同的目标 URL + crawl_config 调用试探性爬取并成功，再提交/重试/应用新范围；'
        f'若刚更换入口或改过 wait_for/css_selector/filter 等参数，必须重新试爬。'
    )


def failed_samples_not_verified_summary(
    candidate_urls: list[str],
    *,
    total_failed: int | None = None,
) -> str:
    """失败修复重试：任务失败页均未用当前配置试爬成功。"""
    hints = '、'.join(candidate_urls[:3]) or '（无举例）'
    total = total_failed if total_failed is not None else len(candidate_urls)
    return (
        f'操作被拒绝：本任务共 {total} 个失败 URL，尚未用本次 crawl_config 对其中任意一个试爬成功'
        f'（举例：{hints}）。请任选一个失败页（不要只用任务入口页）试爬成功后再重试；'
        f'不要求修通全部失败页。改过 wait_for/css_selector/filter 后须重新试爬。'
    )
