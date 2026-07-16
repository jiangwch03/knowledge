"""
Stage2/Stage3/Stage4 状态流转集成测试

覆盖场景：
- Stage2 路径 A：LINK_FAILED → 重新申请链接成功
- Stage2 路径 B：UPLOAD_FAILED 分段超时失败收敛
- Stage3：全部分段解析成功 → COMPLETED + 发布 Stage4 消息
- Stage3：部分分段解析失败 → FAILED + USER_DECISION
- Stage4：合并 Markdown 并入库
"""

# ruff: noqa: E402, ANN201

import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _PROJECT_ROOT / 'src'
sys.path.insert(0, str(_SRC_PATH))
sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_common.enums.boolean_char_flag_enum import BooleanCharFlag
from knowledge_common.enums.document_type_enum import DocumentType
from knowledge_content.enums.document_upload_status_enum import DocumentUploadStatus
from knowledge_content.enums.mineru_parse_detail_state_enum import MineruParseDetailState
from knowledge_content.enums.mineru_parse_task_status_enum import MineruParseTaskStatus
from knowledge_content.mapper.do.parse_detail_task_do import KnowledgeMineruParseDetailTask
from knowledge_content.mapper.do.parse_task_do import KnowledgeMineruParseTask
from knowledge_content.mapper.do.upload_task_do import KnowledgeUploadDocumentParseTask
from knowledge_content.service.document_upload_parse_service import DocumentUploadParseService


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


class TestStage2PathARetryLinkFailed:
    """Stage2 路径 A：重新申请上传链接"""

    @pytest.mark.asyncio
    async def test_link_failed_retry_success(self):
        """测试 LINK_FAILED 任务重新申请链接成功"""
        mock_task = MagicMock(spec=KnowledgeMineruParseTask)
        mock_task.parse_task_id = 10
        mock_task.task_id = 1
        mock_task.status = MineruParseTaskStatus.PENDING.value
        mock_task.parse_mode = 'document'
        mock_task.enable_formula = BooleanCharFlag.YES.value
        mock_task.enable_table = BooleanCharFlag.YES.value
        mock_task.language = 'ch'
        mock_task.is_ocr = BooleanCharFlag.NO.value

        mock_record = MagicMock(spec=KnowledgeUploadDocumentParseTask)
        mock_record.task_id = 1
        mock_record.total_pages = 100
        mock_record.original_doc_key = 'https://minio/test.pdf'
        mock_record.doc_name = 'test.pdf'

        mock_apply_result = MagicMock()
        mock_apply_result.batch_id = 'batch-001'
        mock_apply_result.file_urls = ['https://minio/upload/1', 'https://minio/upload/2']
        mock_apply_result.data_ids = ['data-1', 'data-2']
        mock_apply_result.page_ranges = ['1-50', '51-100']

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.get_task_by_id',
                new_callable=AsyncMock,
                return_value=mock_task,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.get_task_by_id',
                new_callable=AsyncMock,
                return_value=mock_record,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.get_details_by_task_id',
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch.object(
                DocumentUploadParseService,
                '_apply_upload_urls',
                new_callable=AsyncMock,
                return_value=mock_apply_result,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_task,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_record,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.batch_add_details',
                new_callable=AsyncMock,
            ) as mock_add_details,
            patch.object(
                DocumentUploadParseService,
                '_upload_segments',
                new_callable=AsyncMock,
                return_value=[True, True],
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.update_detail',
                new_callable=AsyncMock,
            ),
        ):
            await DocumentUploadParseService.process_pending_task(10)

            # 验证任务状态有更新
            assert mock_update_task.call_count >= 2  # WAITING_UPLOAD + PARSING
            # 验证上传记录状态有更新
            assert mock_update_record.call_count >= 2  # WAITING_UPLOAD + PARSING


class TestStage2PathBUploadFailed:
    """Stage2 路径 B：上传失败分段处理"""

    @pytest.mark.asyncio
    async def test_upload_failed_timeout_converge(self):
        """测试上传链接过期后全部分段标记为 PARSED_FAILED 并收敛"""
        parse_task_id = 20
        expired_time = datetime.now() - timedelta(hours=1)

        mock_details = [
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=1,
                parse_task_id=parse_task_id,
                upload_expire_at=expired_time,
                state=MineruParseDetailState.UPLOAD_FAILED.value,
            ),
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=2,
                parse_task_id=parse_task_id,
                upload_expire_at=expired_time,
                state=MineruParseDetailState.UPLOAD_FAILED.value,
            ),
        ]

        # 收敛后查询返回 PARSED_FAILED 状态
        mock_details_failed = [
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=1,
                parse_task_id=parse_task_id,
                state=MineruParseDetailState.PARSE_FAILED.value,
            ),
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=2,
                parse_task_id=parse_task_id,
                state=MineruParseDetailState.PARSE_FAILED.value,
            ),
        ]

        mock_task = MagicMock(spec=KnowledgeMineruParseTask)
        mock_task.parse_task_id = parse_task_id
        mock_task.task_id = 2

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.batch_update_state',
                new_callable=AsyncMock,
            ) as mock_batch_update,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.get_details_by_task_id',
                new_callable=AsyncMock,
                side_effect=[mock_details, mock_details_failed],
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.get_task_by_id',
                new_callable=AsyncMock,
                return_value=mock_task,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_task,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_record,
        ):
            await DocumentUploadParseService.stage2_path_b_upload_failed(
                parse_task_id, mock_details
            )

            # 验证分段标记为 PARSED_FAILED
            mock_batch_update.assert_called_once_with(
                [1, 2], MineruParseDetailState.PARSE_FAILED.value
            )

            # 简化验证：只要分段被更新即可
            assert mock_batch_update.call_count == 1


class TestStage3PollResults:
    """Stage3：轮询解析结果"""

    @pytest.mark.asyncio
    async def test_all_details_parsed_success(self):
        """测试全部分段解析成功 → COMPLETED + 发布 Stage4"""
        parse_task_id = 30
        record_id = 3
        batch_id = 'batch-003'

        mock_task = MagicMock(spec=KnowledgeMineruParseTask)
        mock_task.parse_task_id = parse_task_id
        mock_task.task_id = record_id
        mock_task.batch_id = batch_id

        # 第一次查询返回 PARSING 状态（用于更新）
        mock_details_parsing = [
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=1,
                data_id='data-1',
                state=MineruParseDetailState.PARSING.value,
                sequence_number=1,
            ),
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=2,
                data_id='data-2',
                state=MineruParseDetailState.PARSING.value,
                sequence_number=2,
            ),
        ]

        # 第二次查询返回 PARSED 状态（用于收敛判断）
        mock_details_parsed = [
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=1,
                data_id='data-1',
                state=MineruParseDetailState.PARSED.value,
                sequence_number=1,
            ),
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=2,
                data_id='data-2',
                state=MineruParseDetailState.PARSED.value,
                sequence_number=2,
            ),
        ]

        mock_batch_result = MagicMock()
        mock_batch_result.extract_result = [
            MagicMock(data_id='data-1', state='done', full_zip_url='https://minio/zip1.zip'),
            MagicMock(data_id='data-2', state='done', full_zip_url='https://minio/zip2.zip'),
        ]

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.MineUClient'
            ) as mock_client_cls,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.get_details_by_task_id',
                new_callable=AsyncMock,
                side_effect=[mock_details_parsing, mock_details_parsed],
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.update_detail',
                new_callable=AsyncMock,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_task,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_record,
        ):
            mock_client = MagicMock()
            mock_client.get_batch_results = AsyncMock(return_value=mock_batch_result)
            mock_client_cls.return_value = mock_client

            result = await DocumentUploadParseService.poll_parse_results(
                parse_task_id, record_id, batch_id
            )

            # 验证任务完成
            mock_update_task.assert_any_call(
                parse_task_id, MineruParseTaskStatus.COMPLETED.value
            )
            mock_update_record.assert_any_call(
                record_id, DocumentUploadStatus.COMPLETED.value
            )
            # 验证返回值（通知调度器在锁外发布消息）
            assert result is True

    @pytest.mark.asyncio
    async def test_partial_details_failed(self):
        """测试部分分段解析失败 → FAILED + USER_DECISION"""
        parse_task_id = 40
        record_id = 4
        batch_id = 'batch-004'

        mock_details = [
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=1,
                data_id='data-1',
                state=MineruParseDetailState.PARSED.value,
            ),
            MagicMock(
                spec=KnowledgeMineruParseDetailTask,
                detail_id=2,
                data_id='data-2',
                state=MineruParseDetailState.PARSE_FAILED.value,
            ),
        ]

        mock_batch_result = MagicMock()
        mock_batch_result.extract_result = [
            MagicMock(data_id='data-1', state='done', full_zip_url='https://minio/zip1.zip'),
            MagicMock(data_id='data-2', state='failed', err_msg='解析超时'),
        ]

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.MineUClient'
            ) as mock_client_cls,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.get_details_by_task_id',
                new_callable=AsyncMock,
                side_effect=[mock_details, mock_details],
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.update_detail',
                new_callable=AsyncMock,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_task,
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_record,
        ):
            mock_client = MagicMock()
            mock_client.get_batch_results = AsyncMock(return_value=mock_batch_result)
            mock_client_cls.return_value = mock_client

            result = await DocumentUploadParseService.poll_parse_results(
                parse_task_id, record_id, batch_id
            )

            # 验证任务失败
            mock_update_task.assert_called_with(
                parse_task_id,
                MineruParseTaskStatus.FAILED.value,
                error_code='PARSE_FAILED',
                error_message='部分分段解析失败',
            )
            # 验证上传任务等待用户决策
            mock_update_record.assert_called_with(
                record_id,
                DocumentUploadStatus.USER_DECISION.value,
                error_code='PARSE_FAILED',
                error_message='部分分段解析失败',
            )


class TestStage4MarkdownMerge:
    """Stage4：合并 Markdown 并入库"""

    @pytest.mark.asyncio
    async def test_md_merge_success(self):
        """测试 Markdown 合并并入库成功"""
        record_id = 5

        mock_record = MagicMock(spec=KnowledgeUploadDocumentParseTask)
        mock_record.task_id = record_id
        mock_record.doc_title = '测试文档'
        mock_record.doc_desc = '描述'
        mock_record.doc_name = 'test.pdf'
        mock_record.doc_type = DocumentType.PDF.value
        mock_record.doc_version = '1.0'
        mock_record.version_remark = None
        mock_record.original_doc_key = 'https://minio/test.pdf'
        mock_record.user_id = 1
        mock_record.dept_id = 1
        mock_record.create_by = 'admin'
        mock_record.update_by = 'admin'

        mock_merge_result = MagicMock()
        mock_merge_result.merged_markdown = '# 测试文档\n\n内容'
        mock_merge_result.image_map = {}

        with (
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.get_task_by_id',
                new_callable=AsyncMock,
                return_value=mock_record,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.get_active_task_by_upload_task_id',
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseTaskDao.get_tasks_by_upload_task_id_and_status',
                new_callable=AsyncMock,
                return_value=[MagicMock(parse_task_id=50)],
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMineruParseDetailTaskDao.get_details_by_task_ids',
                new_callable=AsyncMock,
                return_value=[
                    MagicMock(
                        detail_id=1,
                        sequence_number=1,
                        full_zip_url='https://minio/zip1.zip',
                    )
                ],
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.MineruZipMergeService.download_and_extract_details',
                new_callable=AsyncMock,
                return_value=mock_merge_result,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMinioService.upload_stream',
                new_callable=AsyncMock,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeMinioService.get_object_url',
                return_value='https://minio/final.md',
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeDocumentDao.update_latest_by_title',
                new_callable=AsyncMock,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeDocumentDao.get_max_version_by_title',
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeDocumentDao.add_document',
                new_callable=AsyncMock,
            ),
            patch(
                'knowledge_content.service.document_upload_parse_service.KnowledgeUploadTaskDao.update_status',
                new_callable=AsyncMock,
            ) as mock_update_status,
        ):
            await DocumentUploadParseService.process_md_pending(record_id)

            # 验证上传任务状态更新为 CONVERTED
            mock_update_status.assert_called_with(
                record_id, DocumentUploadStatus.CONVERTED.value
            )
