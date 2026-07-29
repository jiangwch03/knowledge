"""RAG 相关 sys_config 读取（与 Tavily 等同属 sys_config 缓存键）。"""

from __future__ import annotations

from knowledge_common.redis import RedisConnection
from knowledge_common.service.config_service import ConfigService
from knowledge_common.utils.log_util import logger

# 单条文档送入精排 / 分片块大小上限（字符）。qwen3-rerank 官方约 4000 tokens/条，
# 中文粗算约 1 字/token，默认 4000；可在「参数设置」改 rag.rerank.max_doc_chars。
RERANK_MAX_DOC_CHARS_KEY = 'rag.rerank.max_doc_chars'
DEFAULT_RERANK_MAX_DOC_CHARS = 4000


class RagConfigService:
    """从 sys_config（Redis 缓存）读取 RAG 运行参数。"""

    @classmethod
    async def get_rerank_max_doc_chars(cls) -> int:
        """精排单文档最大字符数；未配置或非法时回落默认值。"""
        raw = await cls._get_cached(RERANK_MAX_DOC_CHARS_KEY)
        if raw is None:
            return DEFAULT_RERANK_MAX_DOC_CHARS
        try:
            value = int(str(raw).strip())
        except (TypeError, ValueError):
            logger.warning(
                '[RagConfig] {} 非法值={!r}，回落默认 {}',
                RERANK_MAX_DOC_CHARS_KEY,
                raw,
                DEFAULT_RERANK_MAX_DOC_CHARS,
            )
            return DEFAULT_RERANK_MAX_DOC_CHARS
        if value <= 0:
            return DEFAULT_RERANK_MAX_DOC_CHARS
        return value

    @classmethod
    async def _get_cached(cls, config_key: str) -> str | None:
        try:
            from knowledge_common.common.context import RequestContext

            redis = RequestContext.get_current_request().app.state.redis
        except Exception:
            try:
                redis = await RedisConnection.create_redis_pool(log_enabled=False)
            except Exception:
                return None
        value = await ConfigService.query_config_list_from_cache_services(redis, config_key)
        if value is None:
            return None
        return str(value)
