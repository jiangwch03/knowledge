"""按 prompt_profile 切换系统提示词，并注入知识库引用（与网页来源区分）。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage

from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger
from knowledge_retrieval.agents.utils.llm_util import get_base_chat_model
from knowledge_retrieval.agents.utils.runtime_context_util import context_get_int
from knowledge_retrieval.service.topic_gate_service import TopicGateService
  
# prompt_profile → prompts.yaml 中的 system 提示词 key
_PROFILE_PROMPT_KEY = {
    'knowledge': 'knowledge_qa',
    'cs': 'knowledge_cs',
}


class QaPromptModelMiddleware(AgentMiddleware):
    """wrap_model_call：换模型 + 注入 cs/knowledge 系统提示与检索资料。"""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse | Any]],
    ) -> ModelResponse | Any:
        model_id = self._resolve_model_id(request)
        model = await get_base_chat_model(model_id)

        state = request.state
        if not state:
            raise ServiceException('ModelRequest.state 为空，异常终止')
        profile = state.get('prompt_profile')
        if not profile:
            raise ServiceException('state.prompt_profile 为空，异常终止')
        # 构建系统提示词
        system_prompt = await self._build_system_prompt(profile, state.get('retrieve_hits') or [])
        logger.info('[KnowledgeQA] model call profile={} model_id={}', profile, model_id)

        # 覆盖 system message
        if not request.messages:
            raise ServiceException('ModelRequest.messages 为空，异常终止')
        messages = list(request.messages)
        if isinstance(messages[0], SystemMessage):
            messages[0] = SystemMessage(content=system_prompt)
        else:
            messages = [SystemMessage(content=system_prompt), *messages]

        return await handler(request.override(model=model, messages=messages, system_message=SystemMessage(content=system_prompt)))

    async def _build_system_prompt(self, profile: str, hits: list[dict]) -> str:
        """构建系统提示词。"""
        prompt_key = _PROFILE_PROMPT_KEY.get(profile)
        if not prompt_key:
            raise ServiceException(f'未知 prompt_profile={profile}，异常终止')
        base = prompt_config.get_system_prompt(prompt_key)
        if not base:
            raise ServiceException(f'prompt_config.get_system_prompt("{prompt_key}") 为空，异常终止')

        if profile == 'cs':
            labels = await TopicGateService._load_topic_labels()
            topics = '\n'.join(f'- {x}' for x in labels) or '- （暂未配置可服务主题）'
            return base.replace('{topics}', topics)

        if not hits:
            # 没有检索资料，使用 without_hits 提示词
            without_hits = prompt_config.get('knowledge_qa', field='without_hits')
            if not without_hits:
                raise ServiceException('prompt_config.get("knowledge_qa", field="without_hits") 为空，异常终止')
            return f'{base}\n\n{without_hits}'

        # 有检索资料，注入检索资料
        compact = [
            {
                'index': idx,
                'docId': hit.get('docId') or hit.get('doc_id'),
                'chunkId': hit.get('chunkId') or hit.get('chunk_id'),
                'parentChunkId': hit.get('parentChunkId') or hit.get('parent_chunk_id'),
                'docTitle': hit.get('docTitle') or hit.get('doc_title'),
                'score': hit.get('score'),
                'text': (hit.get('text') or '')[:1200],
                'sourceType': 'knowledge_base',
            }
            for idx, hit in enumerate(hits, start=1)
        ]
        with_hits = prompt_config.get('knowledge_qa', field='with_hits')
        if not with_hits:
            raise ServiceException('prompt_config.get("knowledge_qa", field="with_hits") 为空，异常终止')
        return f'{base}\n\n{with_hits.replace("{hits_json}", json.dumps(compact, ensure_ascii=False))}'

    def _resolve_model_id(self, request: ModelRequest) -> int:
        model_id = context_get_int(request.runtime.context, 'model_id')
        if model_id is None:
            raise ServiceException('runtime.context.model_id 为空，异常终止')
        return model_id


qa_prompt_model_middleware = QaPromptModelMiddleware()
