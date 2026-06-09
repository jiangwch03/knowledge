"""测试 MinerU 客户端方法"""
import asyncio

from baseTest import *

from knowledge_rag.infra.mineru.mineru_client import MineUClient
from knowledge_rag.infra.mineru.vo.mineru_batch_upload_vo import MinerUBatchUploadReqVo, MinerUFileItem
from knowledge_common.utils.log_util import logger


async def test_apply_upload_urls():
    """单独测试 apply_upload_urls"""
    client = MineUClient()

    request = MinerUBatchUploadReqVo(
        files=[
            MinerUFileItem(name='第8节 Prompt GPTs与Assistants API 学生版.pdf', is_ocr=False),
            MinerUFileItem(name='r7-product-manual-20250123.pdf', is_ocr=True),
        ],
        enable_formula=True,
        enable_table=True,
        language='ch',
    )

    result = await client.apply_upload_urls(request)
    print('=' * 60)
    print('apply_upload_urls 返回结果')
    print('=' * 60)
    print(f'batch_id     : {result.batch_id}')
    print(f'file_urls len: {len(result.file_urls)}')
    print(f'file_names   : {result.file_names}')
    print(f'data_ids     : {result.data_ids}')
    print(f'page_ranges  : {result.page_ranges}')
    print('=' * 60)
    return result


async def test_get_batch_results():
    """单独测试 get_batch_results 方法"""
    client = MineUClient()
    batch_id = '00a9f4e8-d27c-45b5-a12c-89b4868c9ca5'
    result = await client.get_batch_results(batch_id)
    logger.info(f'批量任务结果: {result.model_dump()}')
    print(f'批量任务结果: {result.model_dump()}')


if __name__ == '__main__':
    asyncio.run(test_apply_upload_urls())
    # asyncio.run(test_get_batch_results())
