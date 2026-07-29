"""主题闸门：提示词 + 用户问题 → LLM 判断是否走知识库检索。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from knowledge_common.common import with_session
from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.service.dict_service import DictDataService
from knowledge_common.utils.log_util import logger
from knowledge_retrieval.agents.utils.llm_util import get_base_chat_model

TOPIC_DICT_TYPE = 'rag_retrieve_topic'
PromptProfile = Literal['cs', 'knowledge']


class TopicGateResult(BaseModel):
    prompt_profile: PromptProfile = 'cs'


class _GateLlmOut(BaseModel):
    related: bool = Field(default=False, description='问题是否与给定主题相关')


class TopicGateService:
    @classmethod
    async def route(cls, question: str, *, model_id: int | None = None) -> TopicGateResult:
        labels = await cls._load_topic_labels()
        system = prompt_config.get_system_prompt('topic_gate')
        if not labels or not system:
            logger.warning('[TopicGate] 主题字典或提示词缺失，走客服路径')
            return TopicGateResult()

        try:
            topics = '\n'.join(f'- {x}' for x in labels)
            system = system.replace('{topics}', topics)
            model = await get_base_chat_model(model_id)
            raw = await model.with_structured_output(_GateLlmOut).ainvoke(
                [
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': question.strip()},
                ]
            )
            llm_out = raw if isinstance(raw, _GateLlmOut) else _GateLlmOut.model_validate(raw)
            related = llm_out.related
        except Exception as exc:
            logger.opt(exception=True).warning('[TopicGate] 路由失败，走客服路径: {}', exc)
            return TopicGateResult()

        result = TopicGateResult(prompt_profile='knowledge' if related else 'cs')
        logger.info('[TopicGate] related={} prompt_profile={}', related, result.prompt_profile)
        return result

    @classmethod
    @with_session
    async def _load_topic_labels(cls) -> list[str]:
        rows = await DictDataService.query_dict_data_list_services(TOPIC_DICT_TYPE)
        labels: list[str] = []
        for row in rows:
            if getattr(row, 'status', '0') not in (None, '0'):
                continue
            label = getattr(row, 'dict_label', None) or getattr(row, 'dict_value', None)
            if label:
                labels.append(str(label))
        return labels
