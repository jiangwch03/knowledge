"""测试 batch_upload_local_files 方法

测试路径：/Users/jsir/programfiles/pythonProjects/knowledge/knowledge-rag/src/vf_admin/upload_path/mineru/r7-product-manual-20250123.pdf
"""
from pathlib import Path

from baseTest import *
import asyncio

from knowledge_rag.infra.mineru.mineru_client import MineUClient
from knowledge_rag.infra.mineru.vo.mineru_batch_upload_vo import MinerUBatchUploadReqVo
from knowledge_common.utils.log_util import logger

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

_FILE_PATH_1 = str(_PROJECT_ROOT / 'src' / 'vf_admin' / 'upload_path' / 'mineru' / '第8节 Prompt GPTs与Assistants API 学生版.pdf')
_FILE_PATH_2 = str(_PROJECT_ROOT / 'src' / 'vf_admin' / 'upload_path' / 'mineru' / 'r7-product-manual-20250123.pdf')


async def test_request_batch_upload():
    """单独测试 request_batch_upload（验证页数检测、拆分逻辑、data_id 生成）"""
    client = MineUClient()

    request = MinerUBatchUploadReqVo(
        files=[_FILE_PATH_1, _FILE_PATH_2],
        enable_formula=True,
        enable_table=True,
        language='ch',
    )

    result = await client.request_batch_upload(request)
    print('=' * 60)
    print('request_batch_upload 返回结果')
    print('=' * 60)
    print(f'batch_id     : {result.batch_id}')
    print(f'file_urls len: {len(result.file_urls)}')
    print(f'file_paths   : {result.file_paths}')
    print(f'file_names   : {result.file_names}')
    print(f'data_ids     : {result.data_ids}')
    print(f'page_ranges  : {result.page_ranges}')
    print('=' * 60)
    return result


async def test_batch_upload_local_files():
    client = MineUClient()

    request = MinerUBatchUploadReqVo(
        files=[_FILE_PATH_1, _FILE_PATH_2],
        enable_formula=True,
        enable_table=True,
        language='ch',
    )

    result = await client.batch_upload_local_files(request)
    print('=' * 60)
    print('batch_upload_local_files 返回结果')
    print('=' * 60)
    print(f'batch_id       : {result.batch_id}')
    print(f'upload_results : {result.upload_results}')
    print(f'file_urls len  : {len(result.file_urls)}')
    print(f'file_names     : {result.file_names}')
    print(f'data_ids       : {result.data_ids}')
    print(f'page_ranges    : {result.page_ranges}')
    print('=' * 60)
    logger.info(f'批量上传结果: batch_id={result.batch_id}, upload_results={result.upload_results}, file_urls={result.file_urls}')

    # 测试 get_batch_results
    batch_result = await client.get_batch_results(result.batch_id)
    logger.info(f'批量任务结果: {batch_result.model_dump()}')
    print(f'批量任务结果: {batch_result.model_dump()}')


async def test_get_batch_results():
    """单独测试 get_batch_results 方法"""
    client = MineUClient()
    batch_id = '00a9f4e8-d27c-45b5-a12c-89b4868c9ca5'
    result = await client.get_batch_results(batch_id)
    logger.info(f'批量任务结果: {result.model_dump()}')
    print(f'批量任务结果: {result.model_dump()}')


if __name__ == '__main__':
    asyncio.run(test_request_batch_upload())
    # asyncio.run(test_batch_upload_local_files())
    # asyncio.run(test_get_batch_results())
