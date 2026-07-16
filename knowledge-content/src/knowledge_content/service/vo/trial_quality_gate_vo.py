"""试爬质量门禁 VO"""

from pydantic import BaseModel, Field


class TrialQualityGateVo(BaseModel):
    """trial_crawl 质量门禁判定结果"""

    passed: bool = True
    shell_risk: str = 'low'  # low | medium | high
    issues: list[str] = Field(default_factory=list)
    content_preview: str = ''
    word_count: int = 0
    heading_count: int = 0
    link_count: int = 0
    suggestions: list[str] = Field(default_factory=list)
    # 扩链可达性（有 include_patterns 时生效）
    expansion_ok: bool = True
    seed_in_scope: bool = True
    pages_yielded: int = 0
    pages_in_scope: int = 0
    outbound_in_scope_count: int | None = None
    suggested_seed_urls: list[str] = Field(default_factory=list)
