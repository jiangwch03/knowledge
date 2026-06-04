from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiofiles
import httpx
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger

from knowledge_rag.configs.mineru_config import minerUClientConfig
from knowledge_rag.infra.mineru.vo import MinerUBatchResultRespVo
from knowledge_rag.infra.mineru.vo.mineru_batch_upload_vo import (
    MinerUBatchUploadReqVo,
    MinerUBatchUploadRespVo,
    MinerUFileItem,
    MinerUUploadUrlsVo,
    MinerUUploadFilesRespVo, MinerUUploadUrlsVo,
)


class MineUClient:
    """MineU 精准解析 API 客户端"""

    _TIMEOUT: int = 60
    _MAX_PDF_PAGES: int = 200

    def __init__(self) -> None:
        self._config = minerUClientConfig

        parsed = urlparse(self._config.base_url)
        self._api_base = f'{parsed.scheme}://{parsed.netloc}'
        self._batch_upload_url = f'{self._api_base}{self._config.file_urls_uri}'
        self._batch_result_url_template = f'{self._api_base}{self._config.extract_results_uri}/{{batch_id}}'

        self._headers: dict[str, str] = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self._config.token}',
        }

    async def request_batch_upload(self, request: MinerUBatchUploadReqVo) -> MinerUUploadUrlsVo:
        """申请批量上传链接"""
        file_items: list[MinerUFileItem] = []
        resolved_paths: list[Path] = []
        for fp in request.files:
            path = Path(fp)
            if not path.exists():
                raise ServiceException(f'文件不存在: {path}')
            if not path.is_file():
                raise ServiceException(f'路径不是文件: {path}')
            # # PDF 页数前置校验
            # if path.suffix.lower() == '.pdf':
            #     try:
            #         with pypdf.PdfReader(str(path)) as reader:
            #             page_count = len(reader.pages)
            #         if page_count > self._MAX_PDF_PAGES:
            #             raise ServiceException(
            #                 f'PDF 页数超过限制: {path.name} 共 {page_count} 页，'
            #                 f'最大允许 {self._MAX_PDF_PAGES} 页，请拆分文件或指定页码范围'
            #             )
            #     except ServiceException:
            #         raise
            #     except Exception as e:
            #         logger.warning(f'PDF 页数读取失败: {path.name}, error={e}')
            resolved_paths.append(path)
            file_items.append(MinerUFileItem(name=path.name))

        # mineru模型版本 如果解析的是HTML文件 MinerU-HTML，如果是非HTML文件 vlm
        model_version = self._config.resolve_model_version(request.parse_mode)

        payload: dict[str, Any] = {
            'files': [item.model_dump(by_alias=True, exclude_none=True) for item in file_items],
            'model_version': model_version,
            'enable_formula': request.enable_formula,
            'enable_table': request.enable_table,
            'language': request.language,
        }
        # 额外导出格式
        if request.extra_formats is not None:
            payload['extra_formats'] = request.extra_formats

        # 回调地址 回调参数的随机字符串
        if self._config.callback_url and self._config.seed:
            payload['callback'] = self._config.callback_url
            payload['seed'] = self._config.seed

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._batch_upload_url,
                headers=self._headers,
                json=payload,
                timeout=self._TIMEOUT,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get('code') != 0:
                code = result.get('code', 999999)
                msg = result.get('msg', '未知错误')
                trace_id = result.get('trace_id', '未知trace_id')
                logger.error(f'MineU 申请上传链接失败:code={code} msg={msg} trace_id={trace_id}')
                raise ServiceException(f'MineU 申请上传链接失败: code={code} msg={msg} trace_id={trace_id}')

            data = result.get('data', {})
            batch_id = data.get('batch_id', '')
            file_urls = data.get('file_urls', [])

            if not batch_id:
                raise ServiceException('MineU 返回的 batch_id 为空')
            if len(file_urls) != len(resolved_paths):
                raise ServiceException('返回的上传链接数量与文件数量不匹配')

        return MinerUUploadUrlsVo(
            batch_id=batch_id,
            file_urls=file_urls,
            file_paths=[str(p) for p in resolved_paths],
        )

    async def upload_files(self, request: MinerUUploadUrlsVo) -> MinerUUploadFilesRespVo:
        """将本地文件批量上传到预签名链接"""
        upload_results: list[bool] = []
        async with httpx.AsyncClient() as client:
            for idx, file_url in enumerate(request.file_urls):
                file_path = Path(request.file_paths[idx])
                try:
                    upload_resp = await client.put(
                        file_url,
                        content=self._file_chunk_stream(file_path),
                        timeout=360,
                    )
                    success = upload_resp.status_code == 200
                except Exception as upload_err:
                    logger.warning(f'文件上传异常: {file_path.name}, error={upload_err}')
                    success = False

                upload_results.append(success)
                if success:
                    logger.info(f'文件上传成功: {file_path.name}')
                else:
                    logger.warning(f'文件上传失败: {file_path.name}')

        return MinerUUploadFilesRespVo(upload_results=upload_results)

    async def _file_chunk_stream(self, file_path: Path, chunk_size: int = 256 * 1024):
        """异步流式读取文件，内存中仅保留一个 chunk 大小的缓冲区"""
        async with aiofiles.open(file_path, 'rb') as f:
            while chunk := await f.read(chunk_size):
                yield chunk

    async def batch_upload_local_files(self, request: MinerUBatchUploadReqVo) -> MinerUBatchUploadRespVo:
        """本地文件批量上传解析（申请链接 + 上传文件一站式调用）"""
        try:
            urls_resp = await self.request_batch_upload(request)
            logger.info(f'批量上传链接申请成功: {urls_resp}')
            upload_resp = await self.upload_files(urls_resp)
            logger.info(f'文件上传成功: {upload_resp}')
            return MinerUBatchUploadRespVo(
                batch_id=urls_resp.batch_id,
                file_urls=urls_resp.file_urls,
                upload_results=upload_resp.upload_results,
            )
        except ServiceException:
            raise
        except Exception as e:
            logger.error(f'MineU 批量上传解析异常: {e}')
            raise ServiceException(f'MineU 批量上传解析异常: {e}') from e


    async def get_batch_results(self, batch_id: str) -> MinerUBatchResultRespVo:
        """批量获取任务结果"""
        if not batch_id or not batch_id.strip():
            raise ServiceException('batch_id 不能为空')
        try:
            url = self._batch_result_url_template.format(batch_id=batch_id.strip())

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=self._headers, timeout=self._TIMEOUT)
                resp.raise_for_status()
                result = resp.json()

                if result.get('code') != 0:
                    code = result.get('code', 999999)
                    msg = result.get('msg', '未知错误')
                    trace_id = result.get('trace_id', '未知trace_id')
                    logger.error(f'MineU 获取批量任务结果失败:code={code} msg={msg} trace_id={trace_id}')
                    raise ServiceException(f'MineU 获取批量任务结果失败: code={code} msg={msg} trace_id={trace_id}')

                data = result.get('data', {})
                return MinerUBatchResultRespVo.model_validate(data)

        except Exception as e:
            logger.error(f'MinerU 获取批量任务结果异常: {e}')
            raise ServiceException(f'MineU 获取批量任务结果异常: {e}') from e