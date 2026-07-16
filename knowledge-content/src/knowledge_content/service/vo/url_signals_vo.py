"""URL 路径信号 VO"""

from pydantic import BaseModel, Field


class UrlSignalsVo(BaseModel):
    """从 URL 路径提取的版本/语言信号（不依赖页面渲染）"""

    has_version_in_path: bool = False  # URL 路径是否含版本段（如 /v2.6.x/）
    has_language_in_path: bool = False  # URL 路径是否含语言段（如 /zh/、/en-us/）
    version_patterns: list[str] = Field(default_factory=list)  # 匹配到的版本路径片段（最多 5 条）
    language_patterns: list[str] = Field(default_factory=list)  # 匹配到的语言路径片段（最多 5 条）
    path_depth: int = 0  # 路径段数量（不含空段）
