"""单页面分析结果 VO（服务层）"""

from pydantic import BaseModel


class PageAnalysisVo(BaseModel):
    """
    单页面抓取与结构特征分析结果 VO

    由 WebCrawlerAnalysisService.fetch_page 返回，
    对目标页面进行 HTML 解析与特征提取，供上层业务（Agent 工具）消费。
    """

    # 页面标题
    title: str = ''
    # 是否需要 JS 渲染
    has_js_rendering: bool = False
    # 是否有分页
    has_pagination: bool = False
    # 分页类型（page / scroll / load_more / none）
    pagination_type: str = 'none'
    # 是否有弹窗
    has_popup: bool = False
    # 弹窗类型（cookie / login / subscribe / none）
    popup_type: str = 'none'
    # 内容结构概述
    content_structure: str = 'standard'
    # 内链数量
    internal_link_count: int = 0
    # 外链数量
    external_link_count: int = 0
    # 分析失败时的错误信息
    error: str | None = None
