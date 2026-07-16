"""按 runtime context.model_id 动态替换 ChatModel"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse

from knowledge_common.utils.log_util import logger
from knowledge_content.agents.utils.llm_util import get_base_chat_model


class CrawlerModelMiddleware(AgentMiddleware):
    """每次 model 调用前按 runtime context.model_id 解析并替换裸 ChatModel"""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse | Any]],
    ) -> ModelResponse | Any:
        """
        在每次 LLM 调用前按上下文切换模型并透传给下游 handler。

        维护约定：
        - `model_id` 由上游 runtime context 注入（可为空）；
        - 为空或无效时由 get_base_chat_model 内部执行默认模型回退；
        - 这里不做业务兜底，只负责“解析 + 替换 + 记录日志”。
        """
        model_id = self._resolve_model_id(request)
        model = await get_base_chat_model(model_id)
        logger.info('[CrawlerAgent] model call: model_id={}', model_id)
        return await handler(request.override(model=model))

    def _resolve_model_id(self, request: ModelRequest) -> int | None:
        """
        从 runtime context 解析 model_id。

        兼容两类上下文形态：
        - dict: context['model_id']
        - 对象: context.model_id
        """
        context = request.runtime.context
        if context is None:
            return None
        if isinstance(context, dict):
            return context.get('model_id')
        return getattr(context, 'model_id', None)


crawler_model_middleware = CrawlerModelMiddleware()
