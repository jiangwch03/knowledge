"""
AiModelFunctionAdapterService 单元测试
"""

# ruff: noqa: E402, ANN201, ANN202, ANN001, PLC0415

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_PATH = _PROJECT_ROOT / 'src'
sys.path.insert(0, str(_SRC_PATH))
sys.path.insert(0, str(_PROJECT_ROOT))

from knowledge_admin.service.ai_model_function_adapter_service import (
    AiModelFunctionAdapterService,
)
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.vo.ai_model_function_adapter_vo import (
    AiModelConfigModel,
    AiModelFunctionAdapterModel,
    AiModelFunctionAdapterPageQueryModel,
)


def _noop_transactional(*args: Any, **kwargs: Any) -> Callable[[Callable], Callable]:
    """绕过真实事务装饰器，避免测试依赖数据库 Session"""

    def decorator(func: Callable) -> Callable:
        return func

    return decorator


@pytest.fixture(autouse=True)
def _patch_transactional() -> None:
    """每个测试用例前将 service 中的 transactional 替换为透传装饰器"""
    import knowledge_admin.service.ai_model_function_adapter_service as svc_module

    original = svc_module.transactional
    svc_module.transactional = _noop_transactional
    yield
    svc_module.transactional = original


class TestGetAdapterConfig:
    """根据参数ID获取模型配置测试"""

    @pytest.mark.asyncio
    async def test_get_adapter_config_success(self):
        """测试获取模型配置成功"""
        with patch(
            'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_by_param_id',
            new_callable=AsyncMock,
            return_value={
                'adapter_id': 1,
                'function_point': 'TXT转Markdown',
                'param_id': 'txt_to_markdown',
                'model_id': 2,
                'model_code': 'deepseek-chat',
                'model_name': 'DeepSeek Chat',
            },
        ):
            result = await AiModelFunctionAdapterService.get_adapter_config_by_param_id_services(
                'txt_to_markdown'
            )
            assert result.param_id == 'txt_to_markdown'
            assert result.model_code == 'deepseek-chat'

    @pytest.mark.asyncio
    async def test_get_adapter_config_not_found(self):
        """测试参数ID未配置时抛出异常"""
        with patch(
            'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_by_param_id',
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ServiceException) as exc:
                await AiModelFunctionAdapterService.get_adapter_config_by_param_id_services(
                    'not_exist'
                )
            assert '未配置模型适配' in exc.value.message


class TestAdapterList:
    """模型功能适配列表测试"""

    @pytest.mark.asyncio
    async def test_get_adapter_list(self):
        """测试获取适配列表"""
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = 1
        mock_adapter.param_id = 'txt_to_markdown'
        mock_adapter.function_point = 'TXT转Markdown'
        mock_adapter.model_id = 1
        mock_adapter.model_code = 'deepseek-chat'
        mock_adapter.model_name = 'DeepSeek Chat'
        mock_adapter.create_by = 'admin'
        mock_adapter.create_time = None
        mock_adapter.update_by = None
        mock_adapter.update_time = None
        mock_adapter.del_flag = '0'
        
        mock_result = [mock_adapter]
        
        with patch(
            'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_list',
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            query = AiModelFunctionAdapterPageQueryModel()
            result = await AiModelFunctionAdapterService.get_adapter_list_services(query, is_page=False)
            assert isinstance(result, list)
            assert len(result) == 1


class TestAddAdapter:
    """新增模型功能适配测试"""

    @pytest.mark.asyncio
    async def test_add_adapter_success(self):
        """测试新增成功"""
        with (
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.check_param_id_exists',
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelDao.get_ai_model_detail_by_id',
                new_callable=AsyncMock,
                return_value=MagicMock(status='0'),
            ),
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.add_adapter_dao',
                new_callable=AsyncMock,
            ) as mock_add,
        ):
            model = AiModelFunctionAdapterModel(
                function_point='TXT转Markdown',
                param_id='txt_to_markdown',
                model_id=1,
            )
            result = await AiModelFunctionAdapterService.add_adapter_services(model, 'admin')
            assert result.is_success
            assert result.message == '新增成功'
            mock_add.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_adapter_duplicate_param_id(self):
        """测试参数ID重复"""
        with patch(
            'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.check_param_id_exists',
            new_callable=AsyncMock,
            return_value=True,
        ):
            model = AiModelFunctionAdapterModel(
                function_point='TXT转Markdown',
                param_id='txt_to_markdown',
                model_id=1,
            )
            with pytest.raises(ServiceException) as exc:
                await AiModelFunctionAdapterService.add_adapter_services(model, 'admin')
            assert '重复定义' in exc.value.message


class TestEditAdapter:
    """修改模型功能适配测试"""

    @pytest.mark.asyncio
    async def test_edit_adapter_success(self):
        """测试修改成功"""
        with (
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_by_id',
                new_callable=AsyncMock,
                return_value=MagicMock(adapter_id=1),
            ),
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.check_param_id_exists',
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelDao.get_ai_model_detail_by_id',
                new_callable=AsyncMock,
                return_value=MagicMock(status='0'),
            ),
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.edit_adapter_dao',
                new_callable=AsyncMock,
            ) as mock_edit,
        ):
            model = AiModelFunctionAdapterModel(
                adapter_id=1,
                function_point='TXT转Markdown',
                param_id='txt_to_markdown',
                model_id=2,
            )
            result = await AiModelFunctionAdapterService.edit_adapter_services(model, 'admin')
            assert result.is_success
            assert result.message == '修改成功'
            mock_edit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_edit_adapter_not_found(self):
        """测试适配记录不存在"""
        with patch(
            'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_by_id',
            new_callable=AsyncMock,
            return_value=None,
        ):
            model = AiModelFunctionAdapterModel(adapter_id=1)
            with pytest.raises(ServiceException) as exc:
                await AiModelFunctionAdapterService.edit_adapter_services(model, 'admin')
            assert '适配记录不存在' in exc.value.message


class TestDeleteAdapter:
    """删除模型功能适配测试"""

    @pytest.mark.asyncio
    async def test_delete_adapter_success(self):
        """测试删除成功"""
        with (
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_by_id',
                new_callable=AsyncMock,
                return_value=MagicMock(adapter_id=1),
            ),
            patch(
                'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.edit_adapter_dao',
                new_callable=AsyncMock,
            ) as mock_edit,
        ):
            result = await AiModelFunctionAdapterService.delete_adapter_services(1, 'admin')
            assert result.is_success
            assert result.message == '删除成功'
            mock_edit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_adapter_not_found(self):
        """测试适配记录不存在"""
        with patch(
            'knowledge_admin.service.ai_model_function_adapter_service.AiModelFunctionAdapterDao.get_adapter_by_id',
            new_callable=AsyncMock,
            return_value=None,
        ):
            with pytest.raises(ServiceException) as exc:
                await AiModelFunctionAdapterService.delete_adapter_services(1, 'admin')
            assert '适配记录不存在' in exc.value.message
