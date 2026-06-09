import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiofiles
import httpx
import pypdf
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.file_util import FileUtil as FileUtil
from knowledge_rag.configs.mineru_config import minerUClientConfig
from knowledge_rag.infra.mineru.mineru_data_id_generate import generate_data_id, generate_split_data_id
from knowledge_rag.infra.mineru.vo import MinerUBatchResultRespVo
from knowledge_rag.infra.mineru.vo.mineru_batch_upload_vo import (
    MinerUBatchUploadReqVo,
    MinerUBatchUploadRespVo,
    MinerUFileItem,
    MinerULocalFileItem,
    MinerUUploadUrlsVo,
    MinerUUploadFilesRespVo,
)


class MineUClient:
    """MineU 精准解析 API 客户端"""

    _TIMEOUT: int = 60
    _MAX_PAGES: int = 300

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

    def _get_document_page_count(self, path: Path, suffix: str) -> int | None:
        """获取文档页数，支持 PDF 和 DOCX 格式。

        Args:
            path: 文件路径。
            suffix: 文件后缀（小写）。

        Returns:
            文档总页数，若无法获取则返回 None。
        """
        if suffix == '.pdf':
            try:
                reader = pypdf.PdfReader(str(path))
                return len(reader.pages)
            except Exception as e:
                logger.warning(f'PDF 页数读取失败: {path.name}, error={e}')
                return None
        elif suffix == '.docx':
            try:
                with zipfile.ZipFile(path, 'r') as zf:
                    if 'docProps/app.xml' not in zf.namelist():
                        return None
                    with zf.open('docProps/app.xml') as f:
                        root = ET.parse(f).getroot()
                        ns = {'ep': 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'}
                        pages_elem = root.find('ep:Pages', ns)
                        if pages_elem is not None and pages_elem.text:
                            return int(pages_elem.text)
                return None
            except Exception as e:
                logger.warning(f'DOCX 页数读取失败: {path.name}, error={e}')
                return None
        elif suffix == '.doc':
            logger.warning(f'DOC 文件暂不支持自动页数检测: {path.name}')
            return None
        else:
            return None

    def _split_page_ranges(self, total_pages: int, max_pages: int) -> list[tuple[int, int]]:
        """将总页数拆分为多个连续的页码区间。

        Args:
            total_pages: 文档总页数。
            max_pages: 每个区间的最大页数。

        Returns:
            页码区间列表，每个元素为 (start_page, end_page)。
        """
        chunks: list[tuple[int, int]] = []
        start = 1
        while start <= total_pages:
            end = min(start + max_pages - 1, total_pages)
            chunks.append((start, end))
            start = end + 1
        return chunks

    async def _resolve_file_items(
        self, file_items_input: list[MinerULocalFileItem]
    ) -> tuple[list[Path], list[MinerUFileItem]]:
        """解析本地文件项列表，生成 MinerUFileItem，支持大文件按页码拆分。

        若用户未指定页码范围且文档页数超过 _MAX_PAGES，则自动拆分为多个带页码范围的 FileItem，
        并为每个项生成独立的 data_id。

        Args:
            file_items_input: 本地文件项列表。

        Returns:
            (resolved_paths, file_items): 本地路径列表与对应的文件项列表，
            两者长度一致且一一对应。
        """
        resolved_paths: list[Path] = []
        file_items: list[MinerUFileItem] = []

        for item in file_items_input:
            path = Path(item.path)
            if not path.exists():
                raise ServiceException(f'文件不存在: {path}')
            if not path.is_file():
                raise ServiceException(f'路径不是文件: {path}')

            suffix = path.suffix.lower()
            base_data_id = item.data_id or generate_data_id()

            # 用户显式指定了页码范围，直接使用，不再自动拆分
            if item.page_ranges is not None:
                file_items.append(
                    MinerUFileItem(
                        name=path.name,
                        data_id=base_data_id,
                        is_ocr=item.is_ocr,
                        page_ranges=item.page_ranges,
                    )
                )
                resolved_paths.append(path)
                continue

            page_count = self._get_document_page_count(path, suffix)
            if page_count is not None and page_count > self._MAX_PAGES:
                chunks = self._split_page_ranges(page_count, self._MAX_PAGES)
                for idx, (start, end) in enumerate(chunks):
                    page_range = f'{start}-{end}'
                    chunk_data_id = generate_split_data_id(base_data_id, idx + 1, start, end)
                    file_items.append(
                        MinerUFileItem(
                            name=path.name,
                            data_id=chunk_data_id,
                            is_ocr=item.is_ocr,
                            page_ranges=page_range,
                        )
                    )
                    resolved_paths.append(path)
                logger.info(
                    f'文件页数超限已拆分: {path.name} 共 {page_count} 页，'
                    f'拆分为 {len(chunks)} 个任务，每段不超过 {self._MAX_PAGES} 页'
                )
            else:
                file_items.append(
                    MinerUFileItem(
                        name=path.name,
                        data_id=base_data_id,
                        is_ocr=item.is_ocr,
                    )
                )
                resolved_paths.append(path)

        return resolved_paths, file_items

    async def request_batch_upload(self, request: MinerUBatchUploadReqVo) -> MinerUUploadUrlsVo:
        """申请批量上传链接"""
        resolved_paths, file_items = await self._resolve_file_items(request.files)

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
            data_ids=[item.data_id or '' for item in file_items],
            page_ranges=[item.page_ranges for item in file_items],
            file_names=[item.name for item in file_items],
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
                        content=FileUtil.file_chunk_stream(file_path),
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

    

    async def batch_upload_local_files(self, request: MinerUBatchUploadReqVo) -> MinerUBatchUploadRespVo:
        """本地文件批量上传解析（申请链接 + 上传文件一站式调用）"""
        try:
            # 批量上传链接申请
            urls_resp = await self.request_batch_upload(request)
            logger.info(f'批量上传链接申请成功: {urls_resp}')
            # 文件上传
            upload_resp = await self.upload_files(urls_resp)
            logger.info(f'文件上传成功: {upload_resp}')

            return MinerUBatchUploadRespVo(
                batch_id=urls_resp.batch_id,
                file_urls=urls_resp.file_urls,
                upload_results=upload_resp.upload_results,
                data_ids=urls_resp.data_ids,
                page_ranges=urls_resp.page_ranges,
                file_names=urls_resp.file_names,
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