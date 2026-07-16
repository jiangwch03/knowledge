"""页面交互元素 VO（探针③交互归类层输出）"""

from pydantic import BaseModel, Field


class ControlFieldVo(BaseModel):
    """交互元素内的单个表单字段（供 Agent 写 fill hook）"""

    role: str  # username | password | captcha | search_query | filter | unknown
    selector: str  # CSS 选择器
    control_type: str = ''  # text | password | search | ...
    placeholder: str = ''  # 占位提示文本
    label: str = ''  # 关联 label 文本
    options: list[str] = Field(default_factory=list)  # select / radio 可选项


class SubmitControlVo(BaseModel):
    """提交/触发控件（登录按钮、搜索按钮、查询按钮等）"""

    selector: str  # CSS 选择器，供 Agent 写 click/fill hook
    text: str = ''  # 按钮可见文本


class InteractiveElementVo(BaseModel):
    """
    浏览器渲染后探测到的需交互元素（站点无关分类）。

    category 示例：login_gate | search_box | pagination | filter_panel |
    version_switcher | language_switcher | tab_panel | cookie_consent | ...
  """

    category: str  # login_gate | search_box | pagination | version_switcher | ...
    confidence: float = 0.0  # 归类置信度 0~1
    location: str = 'unknown'  # header | sidebar | main | footer | unknown
    evidence: list[str] = Field(default_factory=list)  # 检测依据（DOM 片段、关键词等）
    current_value: str = ''  # 当前选中值（版本/语言/tab 等）
    options: list[str] = Field(default_factory=list)  # 可选项文本列表
    impact: str = ''  # 对爬取的影响简述
    # ③ 归类层扩展：DOM 事实，供 Agent 推理 hooks（探针不写 hooks）
    trigger_mode: str = ''  # instant | submit_on_button | form_submit | manual_query
    mode: str = ''  # pagination: numbered | load_more | infinite_scroll
    fields: list[ControlFieldVo] = Field(default_factory=list)  # 表单字段（登录/搜索等）
    submit: SubmitControlVo | None = None  # 提交/触发按钮
    filters: list[ControlFieldVo] = Field(default_factory=list)  # 筛选面板字段
