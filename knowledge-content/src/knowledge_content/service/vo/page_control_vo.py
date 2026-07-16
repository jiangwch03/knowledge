"""页面 DOM 控件 VO（探针②控件提取层输出）"""

from pydantic import BaseModel, Field


class PageControlVo(BaseModel):
    """
    从渲染后 HTML 提取的单个可交互控件。

    站点无关：任何站的 input/button/select 都走同一套提取规则；
    selector 优先 placeholder/name/type，避免依赖动态 id。
    """

    tag: str  # input | button | select | textarea
    control_type: str = ''  # text | password | search | submit | ...
    placeholder: str = ''  # input placeholder 属性
    name: str = ''  # 表单 name 属性
    control_id: str = ''  # 元素 id（动态 id 不作为 selector 首选）
    text: str = ''  # button 可见文本
    aria_label: str = ''  # aria-label 无障碍标签
    selector: str = ''  # 供 Agent 写 hooks 时引用
    options: list[str] = Field(default_factory=list)  # select 选项文本
