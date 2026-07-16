import threading
from typing import Any, Callable, Sequence

from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from pydantic import BaseModel

from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.vo.langchain_model_vo import (
    ChatModelConfigModel,
    EmbeddingModelConfigModel,
)


class LangChainModelFactory:
    """
    LangChain 大模型实例工厂

    根据模型配置创建 ChatModel / Embeddings 实例，并支持：
    - 动态 provider 路由（OpenAI 协议兼容）
    - 工具（tools）动态绑定
    - 请求重试策略
    """

    DEFAULT_RETRY_ATTEMPTS = 3

    # 全局默认速率限制器（令牌桶），所有 ChatModel 实例共享，避免突发请求触发 API 限流
    # 所有 Agent/Service 共用一个限制器，全局平滑控制 LLM 调用频率，调用方零感知
    _default_rate_limiter: InMemoryRateLimiter = InMemoryRateLimiter(
        requests_per_second=50,        # 每秒最大请求数。50 req/s（≈ 3000/min），覆盖 ReAct 多轮 + 多 agent 并发
        check_every_n_seconds=0.05,    # 令牌桶检查间隔。0.05s = 每秒检查 20 次，匹配 50 req/s 的高频需求
        max_bucket_size=25,            # 令牌桶最大容量。50 req/s 对应 20ms/个令牌，25 个桶 ≈ 0.5s 突发积压
    )

    _chat_model_cache: dict[tuple, BaseChatModel] = {}
    """ChatModel 裸实例缓存（永久单例），key=(model_code,provider,api_key,base_url,temperature,max_tokens)

    仅缓存 init_chat_model 返回的 BaseChatModel，不缓存 tools/retry 绑定结果。
    tools 绑定与 retry 是轻量操作，每次调用时按需执行。
    """
    _chat_model_cache_lock: threading.Lock = threading.Lock()

    @classmethod
    def _make_cache_key(cls, model_config: ChatModelConfigModel) -> tuple:
        """生成 init_chat_model 的缓存 key"""
        return (
            model_config.model_code,
            model_config.provider,
            model_config.api_key,
            model_config.base_url,
            model_config.temperature,
            model_config.max_tokens,
        )

    @classmethod
    def _get_or_create_cached_chat_model(cls, model_config: ChatModelConfigModel) -> BaseChatModel:
        """获取或创建并缓存裸 ChatModel 实例"""
        try:
            key = cls._make_cache_key(model_config)
            model = cls._chat_model_cache.get(key)
            # Cache miss
            if model is None:
                with cls._chat_model_cache_lock:
                    model = cls._chat_model_cache.get(key)
                    if model is None:
                        model = init_chat_model(
                            model=model_config.model_code,
                            model_provider=model_config.provider,
                            api_key=model_config.api_key,
                            base_url=model_config.base_url,
                            temperature=model_config.temperature,
                            max_tokens=model_config.max_tokens,
                            rate_limiter=cls._default_rate_limiter,
                        )
                        cls._chat_model_cache[key] = model
        except Exception as e:
            raise ServiceException(message=f'创建 ChatModel 失败: {e}')

        return model

    @classmethod
    def get_base_chat_model(cls, model_config: ChatModelConfigModel) -> BaseChatModel:
        """
        获取裸 ChatModel 实例（不绑定 tools / retry）

        与 get_chat_model_with_tools_and_retry 共用 init_chat_model 缓存，
        供 create_agent 在 middleware 中按 state 换模型。
        """
        return cls._get_or_create_cached_chat_model(model_config)

    @classmethod
    def get_chat_model_with_tools_and_retry(
        cls,
        model_config: ChatModelConfigModel,
        tools: Sequence[dict[str, Any] | type[BaseModel] | Callable[..., Any] | BaseTool] | None = None,
        structured_output: type[BaseModel] | None = None,
    ) -> Runnable:
        """
        根据模型配置获取可绑定工具且带自动重试的 ChatModel Runnable

        使用 `init_chat_model` 统一初始化，由 LangChain 根据 provider 自动路由到对应的
        integration 包。创建完成后自动附加 `with_retry` 重试策略；若传入 tools/structured_output，
        则在重试之前先绑定工具或结构化输出。

        :param model_config: ChatModel 配置，必须包含 model_code
        :param tools: 可选的工具列表，传入后会先绑定到模型再附加重试
        :param structured_output: 可选的 Pydantic 模型类，传入后先绑定结构化输出再附加重试
        :return: 已绑定工具/结构化输出与重试策略的 Runnable 实例
        :raises ServiceException: model_code 为空或底层创建失败时抛出
        """
        model = cls._get_or_create_cached_chat_model(model_config)
        return cls._bind_tools_and_retry(model, tools, structured_output)

    @classmethod
    def create_embedding_model(cls, model_config: EmbeddingModelConfigModel) -> Embeddings:
        """
        根据模型配置创建 LangChain Embeddings 实例

        使用 `init_embeddings` 统一初始化，仅传递非空参数，避免将 None 透传给底层
        integration 包导致意外行为。

        :param model_config: Embedding 模型配置，必须包含 model_code
        :return: Embeddings 实例
        :raises ServiceException: model_code 为空或底层创建失败时抛出
        """
        params: dict[str, Any] = {
            'model': model_config.model_code,
            'provider': model_config.provider,
        }
        if model_config.api_key:
            params['api_key'] = model_config.api_key
        if model_config.base_url:
            params['base_url'] = model_config.base_url
        if model_config.dimensions:
            params['dimensions'] = model_config.dimensions

        try:
            return init_embeddings(**params)
        except Exception as e:
            raise ServiceException(message=f'创建 Embedding 模型失败: {e}')

    @classmethod
    def bind_tools(
        cls,
        model: BaseChatModel,
        tools: Sequence[dict[str, Any] | type[BaseModel] | Callable[..., Any] | BaseTool],
    ) -> Runnable:
        """
        为已创建的 ChatModel 动态绑定工具列表并附加重试策略

        适用于需要复用同一个 ChatModel 实例、在不同场景绑定不同工具的情况。
        若不需要工具绑定，仅想附加重试，可直接调用底层 `model.with_retry(...)`。

        :param model: 待绑定的 ChatModel 实例（未附加重试的原始实例）
        :param tools: 工具列表，不能为空
        :return: 绑定工具且附带重试策略的 Runnable 实例
        """
        return cls._bind_tools_and_retry(model, tools)

    @classmethod
    def _bind_tools_and_retry(
        cls,
        model: BaseChatModel,
        tools: Sequence[dict[str, Any] | type[BaseModel] | Callable[..., Any] | BaseTool] | None = None,
        structured_output: type[BaseModel] | None = None,
    ) -> Runnable:
        """
        内部方法：可选绑定工具/结构化输出后统一附加指数退避重试策略

        重试参数：
        - stop_after_attempt=3：最多重试 3 次
        - wait_exponential_jitter=True：指数退避 + 随机抖动，避免惊群

        :param model: ChatModel 实例
        :param tools: 可选的工具列表，为 None 时仅附加重试
        :param structured_output: 可选的 Pydantic 模型类，传入后先绑定结构化输出再附加重试
        :return: 处理后的 Runnable 实例
        """
        if tools:
            model = model.bind_tools(tools=tools)

        if structured_output:
            model = model.with_structured_output(structured_output)

        return model.with_retry(
            stop_after_attempt=cls.DEFAULT_RETRY_ATTEMPTS,
            wait_exponential_jitter=True,
        )
