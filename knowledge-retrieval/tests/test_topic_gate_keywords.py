"""主题路由：关键词命中优先，没有主题时回退字典。"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge_retrieval.mapper.dao.retrieve_topic_ro_dao import ActiveTopicBriefVo, ActiveTopicCatalogVo
from knowledge_retrieval.service.topic_gate_service import (
    TopicGateResult,
    TopicGateService,
    format_topic_prompt_lines,
    question_hits_keywords,
)


def test_question_hits_analyzer_keyword():
    assert question_hits_keywords('standard分析器是啥子东东？它咋个处理文本的嘛？', ['分析器'])
    assert question_hits_keywords('STANDARD 是什么', ['standard'])
    assert not question_hits_keywords('今天天气怎么样', ['分析器'])


def test_topic_prompt_includes_description():
    text = format_topic_prompt_lines(
        [
            ActiveTopicBriefVo(topic_name='miluvs主题', description='Milvus 文档，包含 standard 分析器如何切分文本'),
            ActiveTopicBriefVo(topic_name='只有名称'),
        ]
    )

    assert text == '- miluvs主题：Milvus 文档，包含 standard 分析器如何切分文本\n- 只有名称'


@pytest.mark.asyncio
async def test_keyword_hit_skips_topic_model():
    catalog = ActiveTopicCatalogVo(
        topics=[ActiveTopicBriefVo(topic_name='Milvus技术', description='向量库')],
        keywords=['分析器'],
    )
    with (
        patch(
            'knowledge_retrieval.service.topic_gate_service.RetrieveTopicRoDao.list_active_catalog',
            new=AsyncMock(return_value=catalog),
        ),
        patch.object(TopicGateService, '_ask_model', new=AsyncMock()) as ask_model,
    ):
        result = await TopicGateService.route('standard分析器是啥子东东')

    assert result.prompt_profile == 'knowledge'
    ask_model.assert_not_called()


@pytest.mark.asyncio
async def test_keyword_miss_uses_topic_description():
    catalog = ActiveTopicCatalogVo(
        topics=[ActiveTopicBriefVo(topic_name='Milvus技术', description='分析器与索引')],
        keywords=['分析器'],
    )
    ask_model = AsyncMock(return_value=TopicGateResult(prompt_profile='cs'))
    with (
        patch(
            'knowledge_retrieval.service.topic_gate_service.RetrieveTopicRoDao.list_active_catalog',
            new=AsyncMock(return_value=catalog),
        ),
        patch.object(TopicGateService, '_ask_model', new=ask_model),
    ):
        await TopicGateService.route('今天吃什么')

    ask_model.assert_awaited_once()
    passed = ask_model.await_args.args[1]
    assert passed[0].topic_name == 'Milvus技术'
    assert passed[0].description == '分析器与索引'


@pytest.mark.asyncio
async def test_empty_topics_fall_back_to_dictionary():
    ask_model = AsyncMock(return_value=TopicGateResult())
    with (
        patch(
            'knowledge_retrieval.service.topic_gate_service.RetrieveTopicRoDao.list_active_catalog',
            new=AsyncMock(return_value=ActiveTopicCatalogVo()),
        ),
        patch.object(TopicGateService, '_load_topic_labels', new=AsyncMock(return_value=['Milvus技术'])),
        patch.object(TopicGateService, '_ask_model', new=ask_model),
    ):
        await TopicGateService.route('Milvus 是什么')

    assert ask_model.await_args.args[1][0].topic_name == 'Milvus技术'
    assert ask_model.await_args.args[1][0].description == ''
