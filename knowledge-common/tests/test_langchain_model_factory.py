"""
LangChainModelFactory 单元测试
"""

# ruff: noqa: ANN201

import pytest
from langchain.chat_models import init_chat_model
from langchain_core.runnables import Runnable
from langchain_openai import OpenAIEmbeddings

from knowledge_common.common.factory.langchain_model_factory import LangChainModelFactory
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.vo.langchain_model_vo import (
    ChatModelConfigModel,
    EmbeddingModelConfigModel,
)


class TestLangChainModelFactory:
    """LangChain 模型工厂测试"""

    def test_create_openai_model_with_required_params(self):
        """测试使用必填参数创建 OpenAI 模型"""
        model_config = ChatModelConfigModel(
            provider='openai',
            model_code='deepseek-chat',
            api_key='test-api-key',
            base_url='https://test.example.com/v1',
            temperature=0.7,
            max_tokens=2048,
        )
        model = LangChainModelFactory.get_chat_model_with_tools_and_retry(model_config)
        assert isinstance(model, Runnable)

    def test_create_openai_model_with_full_params(self):
        """测试使用完整参数创建 OpenAI 模型"""
        model_config = ChatModelConfigModel(
            provider='openai',
            model_code='qwen3-vl-plus',
            api_key='test-api-key',
            base_url='https://test.example.com/v1',
            temperature=0.5,
            max_tokens=2048,
        )
        model = LangChainModelFactory.get_chat_model_with_tools_and_retry(model_config)
        assert isinstance(model, Runnable)

    def test_missing_model_code_raises_exception(self):
        """测试缺少模型编码时 Pydantic 校验失败"""
        with pytest.raises(Exception):
            ChatModelConfigModel(provider='openai')

    def test_unsupported_provider_raises_exception(self):
        """测试不支持的 provider 抛出异常"""
        with pytest.raises(ServiceException) as exc:
            LangChainModelFactory.get_chat_model_with_tools_and_retry(
                ChatModelConfigModel(
                    provider='anthropic',
                    model_code='claude-3',
                    api_key='test-key',
                    base_url='https://test.example.com/v1',
                    temperature=0.7,
                    max_tokens=2048,
                )
            )
        assert '创建 ChatModel 失败' in exc.value.message

    def test_create_embedding_model(self):
        """测试创建 Embedding 模型：工厂透传 VO 中的调用参数"""
        model_config = EmbeddingModelConfigModel(
            provider='openai',
            model_code='text-embedding-3-small',
            api_key='test-api-key',
            base_url='https://test.example.com/v1',
            dimensions=1536,
            chunk_size=10,
            check_embedding_ctx_length=False,
        )
        model = LangChainModelFactory.create_embedding_model(model_config)
        assert isinstance(model, OpenAIEmbeddings)
        assert model.check_embedding_ctx_length is False
        assert model.chunk_size == 10

    def test_bind_tools(self):
        """测试动态绑定工具"""
        chat_model = init_chat_model(
            model='gpt-4o',
            model_provider='openai',
            api_key='test-api-key',
        )

        def dummy_tool() -> str:
            """示例工具"""
            return 'ok'

        model_with_tools = LangChainModelFactory.bind_tools(chat_model, [dummy_tool])
        assert isinstance(model_with_tools, Runnable)
