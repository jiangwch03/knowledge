from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from knowledge_common.exceptions.exception import ServiceException
from knowledge_common.utils.log_util import logger
from knowledge_common.utils.file_util import FileUtil as FileUtil
from knowledge_content.configs.mineru_config import minerUClientConfig
from knowledge_content.infra.mineru.vo import MinerUBatchResultRespVo
from knowledge_content.infra.mineru.mineru_data_id_generate import generate_data_id_with_prefix, generate_split_data_id
from knowledge_content.infra.mineru.vo.mineru_batch_upload_vo import (
    MinerUFileItem,
    MinerUBatchUploadReqVo,
    MinerUApplyUploadUrlsVo,
    MinerUUploadFilesRespVo,
)


class MineUClient:
    """MineU 精准解析 API 客户端（单例）"""

    _instance = None
    _initialized = False

    _TIMEOUT: int = 60
    _MAX_PAGES: int = 300

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._config = minerUClientConfig

        parsed = urlparse(self._config.base_url)
        self._api_base = f'{parsed.scheme}://{parsed.netloc}'
        self._batch_upload_url = f'{self._api_base}{self._config.file_urls_uri}'
        self._batch_result_url_template = f'{self._api_base}{self._config.extract_results_uri}/{{batch_id}}'

        self._headers: dict[str, str] = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self._config.token}',
        }

    async def apply_upload_urls(self, request: MinerUBatchUploadReqVo) -> MinerUApplyUploadUrlsVo:
        """申请批量上传链接"""
        file_items = request.files

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

        try:
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
                if len(file_urls) != len(file_items):
                    raise ServiceException('返回的上传链接数量与文件数量不匹配')
        except Exception as e:
            logger.error(f'MineU 申请上传链接异常: {e}')
            raise ServiceException(f'MineU 申请上传链接异常: {e}') from e

        return MinerUApplyUploadUrlsVo(
            batch_id=batch_id,
            file_urls=file_urls,
            data_ids=[item.data_id or '' for item in file_items],
            page_ranges=[item.page_ranges for item in file_items],
            file_names=[item.name for item in file_items],
        )

    async def upload_files(self, file_urls: list[str], file_paths: list[str]) -> MinerUUploadFilesRespVo:
        """将本地文件批量上传到预签名链接

        Args:
            file_urls: 文件上传预签名链接列表。
            file_paths: 本地文件路径列表，与 file_urls 一一对应。

        Returns:
            各文件上传是否成功。
        """
        if len(file_urls) != len(file_paths):
            raise ServiceException('上传链接数量与文件路径数量不匹配')

        upload_results: list[bool] = []
        try:
            async with httpx.AsyncClient() as client:
                for idx, file_url in enumerate(file_urls):
                    file_path = Path(file_paths[idx])
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
        except Exception as e:
            logger.error(f'批量上传文件整体异常: {e}')
            raise ServiceException(f'批量上传文件异常: {e}') from e

        return MinerUUploadFilesRespVo(upload_results=upload_results)

    async def download_zip(self, zip_url: str, save_path: Path, timeout: int = 120) -> None:
        """从 MinerU 下载结果 ZIP 包到本地

        Args:
            zip_url: ZIP 下载链接 (full_zip_url)
            save_path: 本地保存路径
            timeout: 下载超时秒数，默认 120s（大文件需要足够时间）
        """
        logger.info(f'下载 MinerU 结果 zip: url={zip_url}, save_to={save_path}')
        async with httpx.AsyncClient() as client:
            resp = await client.get(zip_url, timeout=timeout)
            resp.raise_for_status()
            save_path.write_bytes(resp.content)

    def build_file_items(
        self,
        file_name: str,
        total_pages: int,
        prefix: str,
        is_ocr: bool | None = False,
    ) -> list[MinerUFileItem]:
        """根据总页数构造 MinerUFileItem 列表

        通过 generate_data_id_with_prefix 自动生成 data_id，
        调用方只需提供 prefix 前缀即可，无需手动构造 data_id。

        如果总页数不超过 _MAX_PAGES，返回单个文件项（不分页）；
        否则按 _MAX_PAGES 拆分，每个文件项指定对应的页码范围。

        Args:
            file_name: 文件名，需带正确后缀
            total_pages: 文件总页数
            prefix: data_id 前缀，用于生成业务数据 ID
            is_ocr: 是否启用 OCR

        Returns:
            MinerUFileItem 列表
        """
        if total_pages <= 0:
            raise ServiceException(f'总页数必须大于 0，当前值: {total_pages}')

        base_data_id = generate_data_id_with_prefix(prefix)

        if total_pages <= self._MAX_PAGES:
            return [
                MinerUFileItem(
                    name=file_name,
                    data_id=base_data_id,
                    is_ocr=is_ocr,
                    page_ranges=None,
                )
            ]

        items: list[MinerUFileItem] = []
        part_index: int = 0
        for start in range(1, total_pages + 1, self._MAX_PAGES):
            part_index += 1
            end = min(start + self._MAX_PAGES - 1, total_pages)
            chunk_data_id = generate_split_data_id(base_data_id, part_index, start, end)
            items.append(
                MinerUFileItem(
                    name=file_name,
                    data_id=chunk_data_id,
                    is_ocr=is_ocr,
                    page_ranges=f'{start}-{end}',
                )
            )
        return items

    # 批量获取任务结果
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