from pydantic import BaseModel, Field

from knowledge_content.splitter.vo.text_segment_metadata_vo import TextSegmentMetadataVo


class TextSegmentVo(BaseModel):
    """切分结果片段"""

    text: str = Field(..., description='片段文本内容')
    metadata: TextSegmentMetadataVo = Field(
        default_factory=TextSegmentMetadataVo,
        description='片段元数据（标题路径、业务冗余字段等）',
    )
    skip_embedding: bool = Field(default=False, description='是否跳过向量化（如父块仅作检索上下文）')
    parent_chunk_id: str | None = Field(default=None, description='父分片 ID（子块关联父块时使用）')
    chunk_id: str | None = Field(default=None, description='当前分片唯一 ID')
