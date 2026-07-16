"""
爬取结果后处理服务

负责将 crawl4ai 返回的原始 Markdown 进行后处理：
1. 提取 markdown 中的图片引用
2. 下载图片二进制 → 上传 MinIO
3. 可选：调用 LLM 生成图片描述（替代文本）
4. 替换 markdown 中的图片 URL 为 MinIO 链接
5. 将处理后的 markdown 文件上传 MinIO
6. 返回 object_name 给业务层

图片下载/上传失败不影响整体流程，仅标记单张图片失败并跳过。
"""

import hashlib
import re

import httpx

from knowledge_common.service.llm_chat_service import LlmChatService
from knowledge_common.utils.log_util import logger
from knowledge_content.infra.crawl4ai.vo.crawl4ai_vo import CrawlResultVo
from knowledge_content.service.vo.crawl_processed_vo import CrawlProcessedVo
from knowledge_content.service.minio_service import KnowledgeMinioService

# Markdown 图片语法匹配：![alt_text](url)
_MD_IMAGE_PATTERN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

# 图片下载超时（秒）
_IMAGE_DOWNLOAD_TIMEOUT: int = 30

# 支持的图片格式后缀
_IMAGE_EXTENSIONS: set[str] = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp'}


class CrawlPostProcessorService:

    @classmethod
    async def process_single(cls, task_id: int, result: CrawlResultVo) -> CrawlProcessedVo:
        """
        后处理单个爬取结果

        执行链路：提取图片引用 → 下载图片 → 上传 MinIO → 生成描述 → 替换 markdown → 上传 markdown 到 MinIO

        :param task_id: 任务ID
        :param result: 原始爬取结果
        :return: 处理后的爬取结果（CrawlProcessedVo，不包含原始 markdown/media/links）
        """
        markdown = result.markdown or ''
        url = result.url

        # 步骤1：提取 markdown 中所有图片引用
        image_refs = cls._extract_image_refs(markdown, url)
        logger.info(f'[PostProcessor] 发现 {len(image_refs)} 张图片: task_id={task_id}, url={url}')

        # 步骤2：逐张下载 → 上传 MinIO → 生成描述 → 替换引用
        updated_markdown = markdown
        for alt_text, img_url in image_refs:
            try:
                updated_markdown = await cls._process_single_image(
                    task_id, updated_markdown, alt_text, img_url,
                )
            except Exception as e:
                logger.opt(exception=True).warning('[PostProcessor] 图片处理失败: url={}, error={}', img_url, e)
                # 单张图片失败不影响整体流程，保留原始引用

        # 步骤3：将处理后的 markdown 上传 MinIO
        object_name = await cls._upload_markdown_to_minio(task_id, url, updated_markdown)

        logger.info(f'[PostProcessor] 后处理完成: task_id={task_id}, url={url}, object_name={object_name}')

        # 返回轻量 VO，markdown/media/links 已释放，上层通过 object_name 获取已上传的内容
        return CrawlProcessedVo(
            success=True,
            url=result.url,
            title=result.title,
            status_code=result.status_code,
            object_name=object_name,
        )

    @classmethod
    def _extract_image_refs(cls, markdown: str, page_url: str) -> list[tuple[str, str]]:
        """
        从 Markdown 中提取所有图片引用

        :param markdown: Markdown 内容
        :param page_url: 当前页面 URL，用于将相对路径转为绝对路径
        :return: [(alt_text, absolute_image_url), ...]
        """
        refs: list[tuple[str, str]] = []
        for match in _MD_IMAGE_PATTERN.finditer(markdown):
            alt_text = match.group(1)
            img_url = match.group(2)

            # 跳过 data URI（base64 内联图片）
            if img_url.startswith('data:'):
                continue

            # 相对路径 → 绝对路径
            img_url = cls._resolve_url(page_url, img_url)
            refs.append((alt_text, img_url))

        return refs

    @classmethod
    def _resolve_url(cls, base_url: str, img_url: str) -> str:
        """
        将图片 URL 解析为绝对路径

        :param base_url: 页面基础 URL
        :param img_url: 图片 URL（可能是相对路径或绝对路径）
        :return: 绝对 URL
        """
        if img_url.startswith(('http://', 'https://')):
            return img_url

        # 协议相对路径
        if img_url.startswith('//'):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f'{parsed.scheme}:{img_url}'

        # 根路径相对
        if img_url.startswith('/'):
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            return f'{parsed.scheme}://{parsed.netloc}{img_url}'

        # 当前目录相对路径
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        base_path = parsed.path.rsplit('/', 1)[0] if '/' in parsed.path else ''
        return f'{parsed.scheme}://{parsed.netloc}{base_path}/{img_url}'

    @classmethod
    async def _process_single_image(
        cls,
        task_id: int,
        markdown: str,
        alt_text: str,
        img_url: str,
    ) -> str:
        """
        处理单张图片：下载 → 上传 MinIO → 生成描述 → 替换 markdown

        :param task_id: 任务ID
        :param markdown: 当前 markdown 内容
        :param alt_text: 原始替代文本
        :param img_url: 图片绝对 URL
        :return: 替换后的 markdown
        """
        # 1. 下载图片
        img_bytes, img_ext = await cls._download_image(img_url)

        # 2. 上传至 MinIO
        image_hash = hashlib.md5(img_bytes).hexdigest()[:12]
        object_name = f'crawler/{task_id}/images/{image_hash}.{img_ext}'
        await KnowledgeMinioService.upload_stream(img_bytes, object_name)
        minio_image_url = KnowledgeMinioService.get_object_url(object_name)

        # 3. 生成图片描述（LLM 以 base64 直传图片字节）
        new_alt = alt_text
        if not alt_text or len(alt_text) < 5:
            new_alt = await LlmChatService.generate_image_description_from_bytes(img_bytes, img_ext)

        # 4. 替换 markdown 中的图片引用
        #    先替换 URL 部分：](img_url) → ](minio_image_url)
        markdown = markdown.replace(f']({img_url})', f']({minio_image_url})')
        #    再替换 alt 文本：![old_alt](minio_image_url) → ![new_alt](minio_image_url)
        if new_alt and new_alt != alt_text:
            markdown = markdown.replace(f'![{alt_text}]({minio_image_url})', f'![{new_alt}]({minio_image_url})')

        return markdown

    @classmethod
    async def _download_image(cls, img_url: str) -> tuple[bytes, str]:
        """
        下载图片并返回二进制数据

        :param img_url: 图片绝对 URL
        :return: (图片二进制数据, 格式后缀)
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(img_url, timeout=_IMAGE_DOWNLOAD_TIMEOUT, follow_redirects=True)
            resp.raise_for_status()

        # 从 Content-Type 或 URL 推断格式
        content_type = resp.headers.get('content-type', '')
        img_ext = cls._infer_image_extension(img_url, content_type)

        return resp.content, img_ext

    @classmethod
    def _infer_image_extension(cls, url: str, content_type: str) -> str:
        """
        从 URL 路径或 Content-Type 推断图片格式后缀

        :param url: 图片 URL
        :param content_type: HTTP Content-Type 头
        :return: 格式后缀（如 'png'、'jpg'）
        """
        # 优先从 Content-Type 推断
        if 'png' in content_type:
            return 'png'
        if 'jpeg' in content_type or 'jpg' in content_type:
            return 'jpg'
        if 'gif' in content_type:
            return 'gif'
        if 'webp' in content_type:
            return 'webp'
        if 'svg' in content_type:
            return 'svg'

        # 回退到 URL 后缀
        from urllib.parse import urlparse
        path = urlparse(url).path
        ext = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
        if ext in _IMAGE_EXTENSIONS:
            return ext

        return 'png'  # 默认 png

    @classmethod
    async def _upload_markdown_to_minio(cls, task_id: int, page_url: str, markdown: str) -> str:
        """
        将处理后的 markdown 上传到 MinIO

        :param task_id: 任务ID
        :param page_url: 原始页面 URL，用于生成文件名
        :param markdown: 处理后的 markdown 内容
        :return: MinIO 对象名（object_name）
        """
        # 用 URL hash 作为文件名，避免特殊字符问题
        url_hash = hashlib.md5(page_url.encode()).hexdigest()[:16]
        object_name = f'crawler/{task_id}/pages/{url_hash}.md'

        await KnowledgeMinioService.upload_stream(markdown.encode('utf-8'), object_name)
        return object_name
