"""
MinerU ZIP 下载、解压提取与 Markdown 合并服务

职责：
1. 下载已完成的分段 ZIP 包 → 解压提取 Markdown 内容和图片 → 合并为一个完整 Markdown
2. 将合并后 Markdown 中的本地图片引用替换为 MinIO 可访问 URL

此 Service 与 ORM 解耦，调用方需提供 MineruZipSegmentVo 列表，
适用于任何需要从 MinerU 分段结果合并 Markdown 的场景（文档解析、爬虫解析等）。
"""

import tempfile
import zipfile
from pathlib import Path

from knowledge_common.config.env import MinioConfig, UploadConfig
from knowledge_common.service.llm_chat_service import LlmChatService
from knowledge_common.utils.log_util import logger

from knowledge_content.infra.mineru.mineru_client import MineUClient
from knowledge_content.service.minio_service import KnowledgeMinioService
from knowledge_content.service.vo.mineru_zip_merge_vo import MineruMergeResultVo, MineruZipSegmentVo


class MineruZipMergeService:
    """
    MinerU 结果 ZIP 合并服务

    提供分段 ZIP 下载、Markdown 提取合并、图片引用替换的完整管线。
    所有方法均为类方法，无状态设计，可直接复用。
    """

    # 支持的图片后缀集合
    IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}

    @classmethod
    async def download_and_extract_details(
        cls,
        details: list['MineruZipSegmentVo'],
    ) -> MineruMergeResultVo:
        """
        下载所有分段 ZIP 包，解压提取 Markdown 内容和图片，合并为一个完整 Markdown

        :param details: 已排序的分段合并 VO 列表 （需按 sequence_number 升序）
        :return: MineruMergeResultVo — 包含 merged_markdown（合并后完整 Markdown 内容）
                 和 image_map（图片相对路径到字节数据的映射）
        """
        merged_parts: list[str] = []
        image_map: dict[str, bytes] = {}

        with tempfile.TemporaryDirectory(dir=UploadConfig.UPLOAD_TEMP_PATH) as tmpdir:
            logger.info(f'开始下载并提取解析分段: count={len(details)}, tmpdir={tmpdir}')

            for detail in details:
                if not detail.full_zip_url:
                    logger.warning(
                        f'分段 sequence_number={detail.sequence_number} 无 full_zip_url, 跳过'
                    )
                    continue

                # 1. 下载分段 zip 包到临时目录（委托给 MinerU 客户端）
                zip_path = Path(tmpdir) / f'{detail.sequence_number}.zip'
                await MineUClient().download_zip(detail.full_zip_url, zip_path)

                # 2. 解压 zip 包
                extract_dir = Path(tmpdir) / f'segment_{detail.sequence_number}'
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)

                # 3. 读取分段 Markdown 内容（全量读内存，纯文本即使 300 页 PDF 转出也仅 ~1-3MB，无内存风险）
                md_files = list(extract_dir.rglob('*.md'))
                if md_files:
                    md_content = md_files[0].read_text(encoding='utf-8')
                    merged_parts.append(md_content)
                    logger.info(
                        f'分段 md 已读取: sequence_number={detail.sequence_number}, '
                        f'md_file={md_files[0]}, size={len(md_content)}'
                    )
                else:
                    logger.warning(
                        f'分段无 md 文件: sequence_number={detail.sequence_number}, '
                        f'extract_dir={extract_dir}'
                    )

                # 4. 收集分段中的图片文件
                #     后续用途：①上传 MinIO 供前端展示；②以 base64 喂给 LLM 生成图片描述
                for img_path in extract_dir.rglob('*'):
                    if img_path.is_file() and img_path.suffix.lower() in cls.IMAGE_EXTENSIONS:
                        # 相对于解压目录的 POSIX 路径，用于匹配 Markdown 中的图片引用语法 ![](rel_path)
                        rel_path = img_path.relative_to(extract_dir).as_posix()
                        # 读为原始字节：上传 MinIO 需要字节流，LLM 生成描述需要转 base64
                        image_map[rel_path] = img_path.read_bytes()

            logger.info(
                f'下载提取完成: tmpdir={tmpdir}, '
                f'merged_parts={len(merged_parts)}, images={len(image_map)}'
            )

        return MineruMergeResultVo(
            merged_markdown='\n\n'.join(merged_parts), image_map=image_map
        )

    @classmethod
    async def replace_image_references(
        cls,
        markdown: str,
        image_map: dict[str, bytes],
        record_id: int,
    ) -> str:
        """
        替换 Markdown 中的图片引用为 MinIO URL，并生成图片描述替代文本

        遍历图片映射，对每张图片依次：
          1. 上传至 MinIO 获取公网可访问 URL
          2. 以 base64 图片字节调用 LLM 生成图片语义描述（MinIO 内网 URL 对 LLM 不可达）
          3. 将 Markdown 中的图片源路径替换为 MinIO URL
          4. 将替换后的图片替代文本（原为 rel_path）替换为 LLM 生成的语义描述

        :param markdown: 原始合并后的 Markdown 内容（含相对路径图片引用）
        :param image_map: 图片相对路径到字节数据的映射
        :param record_id: 文档上传记录 ID，用于构造 MinIO 对象路径
        :return: 图片引用和替代文本全部替换完成后的 Markdown 内容
        """
        updated_markdown = markdown

        for rel_path, img_bytes in image_map.items():
            # 1. 上传图片至 MinIO，获取公网可访问 URL
            object_name = (
                f'{MinioConfig.minio_object_image_prefix}/{record_id}/{rel_path}'
            )
            await KnowledgeMinioService.upload_stream(img_bytes, object_name)
            image_url = KnowledgeMinioService.get_object_url(object_name)

            # 2. 以 base64 格式直传图片字节给 LLM 生成语义描述
            #    （MinIO 内网 URL 对 LLM 不可达，故不能传 URL 而需传图片本身）
            image_format = rel_path.rsplit('.', 1)[-1].lower()
            alt_text = await LlmChatService.generate_image_description_from_bytes(
                img_bytes, image_format
            )

            # 3. 将 Markdown 中的图片源路径 `](rel_path)` 替换为 MinIO URL `](image_url)`
            #    此为 Markdown 图片语法 ![](rel_path) 中的 URL 部分替换
            updated_markdown = updated_markdown.replace(
                f']({rel_path})', f']({image_url})'
            )
            # 4. 将替换后的图片替代文本 `![rel_path]` 替换为 LLM 生成的语义描述 `![alt_text]`
            #    注意：此步必须在 URL 替换之后执行，因为替换后的语法为 `![rel_path](image_url)`
            updated_markdown = updated_markdown.replace(
                f'![{rel_path}]({image_url})', f'![{alt_text}]({image_url})'
            )

        return updated_markdown
