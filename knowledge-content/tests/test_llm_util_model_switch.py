"""llm_util 模型切换单元测试"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge_common.vo.ai_model_function_adapter_vo import AiModelConfigModel
from knowledge_content.agents.utils import llm_util


def _adapter(model_id: int, model_code: str) -> AiModelConfigModel:
    return AiModelConfigModel(
        model_id=model_id,
        model_code=model_code,
        provider='openai',
        api_key='k',
        base_url='https://example.com/v1',
        temperature=0.7,
        max_tokens=4096,
    )


@pytest.mark.asyncio
async def test_get_model_config_matches_model_id():
    adapters = [_adapter(1, 'gpt-default'), _adapter(99, 'gpt-alt')]

    with patch.object(llm_util, '_load_crawler_adapters', AsyncMock(return_value=adapters)):
        config = await llm_util._get_model_config(99)

    assert config.model_code == 'gpt-alt'


@pytest.mark.asyncio
async def test_get_model_config_falls_back_when_model_id_missing():
    adapters = [_adapter(1, 'gpt-default'), _adapter(99, 'gpt-alt')]

    with patch.object(llm_util, '_load_crawler_adapters', AsyncMock(return_value=adapters)):
        config = await llm_util._get_model_config(404)

    assert config.model_code == 'gpt-default'


@pytest.mark.asyncio
async def test_get_model_config_uses_default_when_model_id_none():
    adapters = [_adapter(1, 'gpt-default'), _adapter(99, 'gpt-alt')]

    with patch.object(llm_util, '_load_crawler_adapters', AsyncMock(return_value=adapters)):
        config = await llm_util._get_model_config(None)

    assert config.model_code == 'gpt-default'
