"""
DocumentUploadParseService 单元测试
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
from knowledge_content.service.document_upload_parse_service import DocumentUploadParseService
from knowledge_content.enums.parse_decision_action_enum import ParseDecisionAction
from knowledge_content.vo.document_upload_parse_vo import HandleParseDecisionModel, UploadDocumentModel


def _noop_transactional(*args, **kwargs):
    """绕过真实事务装饰器，避免测试依赖数据库 Session"""

    def decorator(func):
        return func

    return decorator


@pytest.fixture(autouse=True)
def _patch_transactional():
    """每个测试用例前将 document_upload_parse_service 中的 transactional 替换为透传装饰器"""
    import knowledge_content.service.document_upload_parse_service as svc_module

    original = svc_module.transactional
    svc_module.transactional = _noop_transactional
    yield
    svc_module.transactional = original


class TestDocumentUploadParseServiceHelpers:
    """DocumentUploadParseService 工具方法测试"""

    def test_get_file_extension(self):
        """测试文件后缀提取"""
        assert DocumentUploadParseService._get_file_extension('test.PDF') == 'pdf'
        assert DocumentUploadParseService._get_file_extension('old.doc') == 'doc'
        assert DocumentUploadParseService._get_file_extension('report.docx') == 'docx'
        assert DocumentUploadParseService._get_file_extension('data.XLSX') == 'xlsx'
        assert DocumentUploadParseService._get_file_extension('note.md') == 'md'

    def test_is_supported(self):
        """测试支持的文件类型判断"""
        assert DocumentUploadParseService._is_supported('pdf')
        assert DocumentUploadParseService._is_supported('doc')
        assert DocumentUploadParseService._is_supported('docx')
        assert DocumentUploadParseService._is_supported('xlsx')
        assert DocumentUploadParseService._is_supported('md')
        assert not DocumentUploadParseService._is_supported('txt')
        assert not DocumentUploadParseService._is_supported('png')
        assert not DocumentUploadParseService._is_supported('')

    def test_resolve_next_version(self):
        """测试版本号递增逻辑"""
        assert DocumentUploadParseService._resolve_next_version(None) == '1.0'
        assert DocumentUploadParseService._resolve_next_version('') == '1.0'
        assert DocumentUploadParseService._resolve_next_version('1.0') == '2.0'
        assert DocumentUploadParseService._resolve_next_version('2.5') == '3.0'
        assert DocumentUploadParseService._resolve_next_version('invalid') == '1.0'


class TestHandleParseDecision:
    """用户决策测试"""

    @pytest.mark.asyncio
    async def test_decision_delete_success(self):
        """测试用户选择删除"""
        async def mock_get_task(_):
            task = MagicMock()
            task.record_id = 1
            task.status = 'FAILED'
            return task

        mock_user = MagicMock()
        mock_user.user.user_name = 'admin'

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.get_task_by_id',
                new_callable=AsyncMock,
                side_effect=mock_get_task,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadRecordDao.get_record_by_id',
                new_callable=AsyncMock,
                return_value=MagicMock(record_id=1),
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeDocumentDao.get_document_by_record_id',
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadRecordDao.soft_delete',
                new_callable=AsyncMock,
            ) as mock_delete_record,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.soft_delete_by_record_id',
                new_callable=AsyncMock,
            ) as mock_delete_task,
            patch(
                'knowledge_content.service.document_upload_parse_service.RequestContext.get_current_user',
                return_value=mock_user,
            ),
        ):
            decision = HandleParseDecisionModel(action=ParseDecisionAction.DELETE)
            decision.userInfo = MagicMock()
            decision.userInfo.user.user_name = 'admin'
            
            await DocumentUploadParseService.handle_parse_decision(1, decision)
            mock_delete_record.assert_awaited_once()
            mock_delete_task.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_decision_retry_invalid_status(self):
        """测试非 FAILED 状态不可重试"""
        async def mock_get_task(_):
            task = MagicMock()
            task.record_id = 1
            task.status = 'PENDING'
            return task

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.get_task_by_id',
                new_callable=AsyncMock,
                side_effect=mock_get_task,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadRecordDao.get_record_by_id',
                new_callable=AsyncMock,
                return_value=MagicMock(record_id=1, status='USER_DECISION'),
            ),
        ):
            decision = HandleParseDecisionModel(action=ParseDecisionAction.RETRY)
            decision.userInfo = MagicMock()
            decision.userInfo.user.user_name = 'admin'
            
            with pytest.raises(ServiceException) as exc:
                await DocumentUploadParseService.handle_parse_decision(1, decision)
            assert '仅 FAILED 状态任务可重试' in exc.value.message
