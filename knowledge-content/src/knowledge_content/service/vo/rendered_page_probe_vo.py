"""渲染探针完整结果 VO"""

from pydantic import BaseModel, Field

from knowledge_content.service.vo.interactive_element_vo import InteractiveElementVo
from knowledge_content.service.vo.page_control_vo import PageControlVo
from knowledge_content.service.vo.page_structure_vo import PageStructureVo
from knowledge_content.service.vo.rendering_probe_vo import RenderingProbeVo
from knowledge_content.service.vo.site_type_candidate_vo import SiteTypeCandidateVo
from knowledge_content.service.vo.suggested_crawl_action_vo import VersionUrlPatternVo
from knowledge_content.service.vo.url_signals_vo import UrlSignalsVo


class RenderedPageProbeVo(BaseModel):
    """
    渲染探针工具返回体。

    流水线：page_structure(①) → controls(②) → interactive_elements(③)
           → site_type_candidates(④) → crawl_implications
    version_url_patterns 为事实；策略由 Planning Agent 根据本 JSON 推理。
    """

    url: str = ''  # 探针目标 URL
    title: str = ''  # 页面标题（截断至 200 字符）
    rendering: RenderingProbeVo = Field(default_factory=RenderingProbeVo)  # HTTP 与浏览器渲染对比（mode / shell_risk / needs_browser）
    url_signals: UrlSignalsVo = Field(default_factory=UrlSignalsVo)  # URL 路径信号，不依赖页面渲染
    page_structure: PageStructureVo = Field(default_factory=PageStructureVo)  # ① crawl4ai 结构化事实（链接规模、正文量等）
    controls: list[PageControlVo] = Field(default_factory=list)  # ② DOM 可交互控件（input / button / select）
    interactive_elements: list[InteractiveElementVo] = Field(default_factory=list)  # ③ 交互语义归类（login_gate / search_box / pagination 等）
    version_url_patterns: list[VersionUrlPatternVo] = Field(default_factory=list)  # ⑤ 版本 URL 事实（非策略，供 Agent 推理 scope）
    site_type_candidates: list[SiteTypeCandidateVo] = Field(default_factory=list)  # ④ 站点类型候选及置信度（最终类型由 Agent 决策）
    crawl_implications: list[str] = Field(default_factory=list)  # 爬取含义短标签（Agent 速览索引，细节见上方各层）
    error: str | None = None  # 浏览器探针失败且无可见正文时的错误信息
    probe_status: str = 'ok'  # ok | blocked
    block_reason: str | None = None  # login_redirect | login_required | captcha_required
    intended_url: str | None = None  # 用户真正想探的 URL（从重定向参数或请求 URL 解析）
    actual_url: str | None = None  # 浏览器实际打开的 URL
    action_required: str | None = None  # ask_user_then_trial_with_hooks
