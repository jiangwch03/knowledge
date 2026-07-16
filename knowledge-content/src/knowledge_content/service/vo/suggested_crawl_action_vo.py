"""探针推导的可执行爬取建议 VO"""

from pydantic import BaseModel, Field


class VersionUrlPatternVo(BaseModel):
    """从渲染后页面链接中提取的版本 URL 模式"""

    version_label: str  # 如 v2.6.x
    url_prefix: str  # 如 https://example.com/docs/zh/v2.6.x
    include_pattern: str  # 如 https://example.com/docs/zh/v2.6.x/*
    sample_href: str = ''  # 页面中匹配到的示例链接
    evidence: str = ''  # 提取依据（如链接文本、DOM 上下文）


class SuggestedCrawlActionVo(BaseModel):
    """探针自动推导的爬取动作（非 LLM 猜测）"""

    action_type: str  # url_prefix | hooks | ask_user
    target: str = ''  # version_label 或 language
    reason: str = ''  # 推导理由
    # action_type=url_prefix 时填充
    url_prefix: str = ''  # 建议爬取 URL 前缀
    include_pattern: str = ''  # 建议 include 通配模式
    start_url: str = ''  # 建议起始 URL
    # action_type=hooks 时填充（从 DOM 推导）
    hooks: dict = Field(default_factory=dict)  # 预填 hook 配置（click / fill / wait 等）
