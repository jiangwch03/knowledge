"""爬取后处理结果 VO（服务层）"""

from pydantic import BaseModel


class CrawlProcessedVo(BaseModel):
    """
    后处理完成的爬取结果 VO

    由 CrawlPostProcessorService 对原始 CrawlResultVo 后处理后产出，供上层业务消费。
    不包含原始 markdown/media/links（已上传 MinIO 并释放内存），
    仅在处理失败（爬取失败或上传失败）时保留 error_code / error_message 供上层感知异常。

    process_single 返回 → pipeline 收集 → executor 编排 → url_record / document 落库
    """

    # 是否处理成功（爬取+后处理+上传全链路成功）
    success: bool
    # 爬取的目标 URL
    url: str
    # 重试场景下该URL已在上次执行中全链路成功，本次跳过后处理
    skipped: bool = False
    # 爬取成功时的页面标题
    title: str | None = None
    # HTTP 状态码（有响应时）
    status_code: int | None = None
    # 后处理完成后的 MinIO 对象名（由 CrawlPostProcessorService 填充）
    object_name: str | None = None
    # 处理失败时的错误码（爬取失败/上传失败等）
    error_code: str | None = None
    # 处理失败时的错误信息（爬取失败/上传失败等）
    error_message: str | None = None
