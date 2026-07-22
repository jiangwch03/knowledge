from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class TextSegmentMetadataVo(BaseModel):
    """切分片段元数据（落库 JSON / 预览返回）。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    # Markdown 标题路径（# ~ ######）
    title: str | None = Field(default=None, description='一级标题 (#)')
    subtitle: str | None = Field(default=None, description='二级标题 (##)')
    section: str | None = Field(default=None, description='三级标题 (###)')
    subsection: str | None = Field(default=None, description='四级标题 (####)')
    subsubsection: str | None = Field(default=None, description='五级标题 (#####)')
    subsubsubsection: str | None = Field(default=None, description='六级标题 (######)')
    header_level: int | None = Field(default=None, description='当前标题层级深度 1-6')

    # 分片标识（与 TextSegmentVo 顶层字段同步写入，便于 JSON 自洽）
    chunk_id: str | None = Field(default=None, description='当前分片 ID')
    parent_chunk_id: str | None = Field(default=None, description='父分片 ID')
    skip_embedding: bool | None = Field(default=None, description='是否跳过向量化')

    # 落库时由 DocumentSplitService 补充
    doc_id: int | None = Field(default=None, description='文档 ID')
    file_id: int | None = Field(default=None, description='文件 ID')
    task_id: int | None = Field(default=None, description='向量化任务 ID')
    release_tag: str | None = Field(default=None, description='发布标签 canary/prod/pending_delete')
    doc_title: str | None = Field(default=None, description='文档标题')
    doc_version: str | None = Field(default=None, description='文档版本')
    file_name: str | None = Field(default=None, description='文件名')
    source_url: str | None = Field(default=None, description='来源 URL')
