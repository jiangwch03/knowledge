"""主题闸门：关键词命中优先，未命中再交给主题模型。"""

from __future__ import annotations

from typing import Literal

import jieba
from pydantic import BaseModel, Field

from knowledge_common.config.prompt_config import prompt_config
from knowledge_common.service.dict_service import DictDataService
from knowledge_common.utils.log_util import logger
from knowledge_retrieval.agents.utils.llm_util import get_base_chat_model
from knowledge_retrieval.mapper.dao.retrieve_topic_ro_dao import ActiveTopicBriefVo, RetrieveTopicRoDao

TOPIC_DICT_TYPE = 'rag_retrieve_topic'
PromptProfile = Literal['cs', 'knowledge']


class TopicGateResult(BaseModel):
    prompt_profile: PromptProfile = 'cs'


class _GateLlmOut(BaseModel):
    related: bool = Field(default=False, description='问题是否与给定主题相关')


def format_topic_prompt_lines(topics: list[ActiveTopicBriefVo]) -> str:
    """主题名称必带；有描述时跟在名称后面。"""
    lines: list[str] = []
    for topic in topics:
        name = topic.topic_name.strip()
        if not name:
            continue
        description = (topic.description or '').strip()
        if description:
            lines.append(f'- {name}：{description}')
        else:
            lines.append(f'- {name}')
    return '\n'.join(lines)


def question_hits_keywords(question: str, keywords: list[str]) -> bool:
    """问句按 jieba 切开后，是否命中主题关键词。"""
    folded = {item.strip().casefold() for item in keywords if item and item.strip()}
    if not folded or not question or not question.strip():
        return False
    for token in jieba.lcut(question):
        text = token.strip()
        if text and text.casefold() in folded:
            return True
    return False


class TopicGateService:
    @classmethod
    async def route(cls, question: str, *, model_id: int | None = None) -> TopicGateResult:
        catalog = await RetrieveTopicRoDao.list_active_catalog()
        if catalog.topics:
            if question_hits_keywords(question, catalog.keywords):
                logger.info('[TopicGate] keyword hit prompt_profile=knowledge')
                return TopicGateResult(prompt_profile='knowledge')
            topics = catalog.topics
        else:
            topics = [ActiveTopicBriefVo(topic_name=label) for label in await cls._load_topic_labels()]
        return await cls._ask_model(question, topics, model_id=model_id)

    @classmethod
    async def _ask_model(cls, question: str, topics: list[ActiveTopicBriefVo], *, model_id: int | None) -> TopicGateResult:
        system = prompt_config.get_system_prompt('topic_gate')
        topic_text = format_topic_prompt_lines(topics)
        if not topic_text or not system:
            logger.warning('[TopicGate] 主题或提示词缺失，走客服路径')
            return TopicGateResult()

        try:
            system = system.replace('{topics}', topic_text)
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
