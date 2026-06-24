"""
MinerU ZIP 分段合并 VO

封装下载 MinerU 结果 ZIP 包时所需的字段，
使 MineruZipMergeService 不直接依赖 ORM 模型 KnowledgeMineruParseDetailTask，
实现服务层与 ORM 的解耦。
"""

from pydantic import BaseModel, Field


class MineruZipSegmentVo(BaseModel):
    """
    MinerU 解析分段 ZIP 合并 VO

    承载下载单个 MinerU 分段结果 ZIP 包所需的最小字段集合，
    用于 MineruZipMergeService 的 download_and_extract_details 方法。
    """

    sequence_number: int = Field(..., description='分段序号，用于排序和临时目录命名')
    full_zip_url: str = Field(..., description='MinerU 结果 ZIP 下载链接')


class MineruMergeResultVo(BaseModel):
    """
    download_and_extract_details 返回结果 VO

    承载合并后的完整 Markdown 内容与图片相对路径到字节数据的映射。
    """

    merged_markdown: str = Field(..., description='合并后的完整 Markdown 内容')
    image_map: dict[str, bytes] = Field(
        default=dict,
        description='图片相对路径到字节数据的映射，用于后续上传 MinIO 和 LLM 生成描述',
    )
