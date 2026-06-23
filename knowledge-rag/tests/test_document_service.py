"""
DocumentService 单元测试
"""

# ruff: noqa: E402, ANN201

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _PROJECT_ROOT / 'src'
sys.path.insert(0, str(_SRC_PATH))
sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_common.exceptions.exception import ServiceException
from knowledge_rag.service.document_service import DocumentService
from knowledge_rag.vo.document_vo import TxtToMarkdownModel


class TestTxtToMarkdown:
    """TXT 转 Markdown 测试"""

    @pytest.mark.asyncio
    async def test_txt_to_markdown_success(self):
        """测试 TXT 转 Markdown 成功"""
        mock_result = '# Hello\n\nWorld'
        
        with patch(
            'knowledge_common.service.llm_chat_service.LlmChatService.txt_to_markdown',
            new_callable=AsyncMock,
            return_value=mock_result,
        ) as mock_llm:
            model = TxtToMarkdownModel(content='Hello World')
            result = await DocumentService.txt_to_markdown(model)
            assert result == '# Hello\n\nWorld'
            mock_llm.assert_awaited_once_with('Hello World')

    @pytest.mark.asyncio
    async def test_txt_to_markdown_exceeds_size_limit(self):
        """测试文本超过 512KB 限制"""
        large_content = 'a' * (512 * 1024 + 1)
        model = TxtToMarkdownModel(content=large_content)
        with pytest.raises(ServiceException) as exc:
            await DocumentService.txt_to_markdown(model)
        assert '文本内容超过 512KB' in str(exc.value)

    @pytest.mark.asyncio
    async def test_txt_to_markdown_missing_adapter(self):
        """测试缺少模型适配配置"""
        with patch(
            'knowledge_common.service.llm_chat_service.LlmChatService.txt_to_markdown',
            new_callable=AsyncMock,
            side_effect=ServiceException('未找到 txt_to_markdown 模型适配配置'),
        ):
            model = TxtToMarkdownModel(content='Hello')
            with pytest.raises(ServiceException) as exc:
                await DocumentService.txt_to_markdown(model)
            assert '未找到 txt_to_markdown 模型适配配置' in exc.value.message
