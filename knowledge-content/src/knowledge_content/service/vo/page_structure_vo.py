"""crawl4ai 结构化页面事实 VO（探针①底座层输出）"""

from pydantic import BaseModel, Field


class LinkSampleVo(BaseModel):
    """内链/外链样本，供 Agent 判断导航与 BFS seed"""

    href: str = ''  # 链接绝对或相对地址
    text: str = ''  # 锚文本（截断后）


class PageStructureVo(BaseModel):
    """
    crawl4ai 一次 arun 的结构化摘要。

    不解读业务含义，只汇总链接规模、元数据、正文量等硬事实。
    """

    title: str = ''  # 页面 <title>
    description: str = ''  # meta description
    markdown_chars: int = 0  # 正文 Markdown 字符数
    html_chars: int = 0  # 渲染后 HTML 字符数
    internal_link_count: int = 0  # 站内链接总数
    external_link_count: int = 0  # 站外链接总数
    internal_link_samples: list[LinkSampleVo] = Field(default_factory=list)  # 内链样本（供 BFS seed 参考）
    table_count: int = 0  # 页面表格数量
    image_count: int = 0  # 页面图片数量
    status_code: int | None = None  # HTTP 状态码
    redirected_url: str | None = None  # 最终跳转 URL（若有重定向）
