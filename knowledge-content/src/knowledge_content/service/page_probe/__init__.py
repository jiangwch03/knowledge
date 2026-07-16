"""
页面探针子包（page_probe）

爬虫 Planning Agent 的「眼睛」层：用浏览器渲染后的页面提取结构化事实，
供 Agent 推理爬取策略（hooks、filter_chain、是否 ask_user 等）。

核心原则
--------
探针 = 眼睛，Agent = 大脑，trial = 裁判。

- 探针只输出 DOM 事实与含义标签，不预生成 hooks / suggested_actions
- 站点无关的通用启发式，不做「知乎专用」「Milvus 专用」定制
- 编排入口在上一级：``rendered_page_probe_service.RenderedPageProbeService``
- 对外工具：``agents.tools.probe_rendered_page.probe_rendered_page``

五层流水线
----------
::

    URL
     ├─ HTTP 快探（与浏览器对比文本量）
     └─ crawl4ai 浏览器探针
           │
           ├─ ① page_structure      crawl4ai_probe_adapter
           ├─ ② controls            control_extractor
           ├─ ③ interactive_elements interaction_classifier (+ 子模块)
           ├─ ④ site_type_candidates site_type_scorer
           ├─ ⑤ version_url_patterns probe_action_planner / version_url_extractor
           └─ crawl_implications    crawl_implications_engine

横切分析（贯穿多层）：

- ``rendering_analyzer``   — HTTP vs 渲染文本量 → spa/ssr/hybrid、shell_risk、needs_browser
- ``url_signals_analyzer`` — URL 路径中的版本段 / 语言段

模块一览
--------
crawl4ai_probe_adapter
    ① 将 crawl4ai ``probe_page`` 结果适配为 PageStructureVo
    （标题、内链数、markdown 字数、链接样本、状态码等）。

control_extractor
    ② 从 HTML 批量抽取 input / button / select / textarea 及 CSS selector。
    只做 DOM 事实，不做业务语义判断。

interaction_classifier
    ③ 交互归类主入口。基于控件 + 页面结构识别：

    - login_gate（含 fields / submit）
    - search_box
    - pagination
    - filter_panel（须真实 ``<select>``，避免 HTML 关键词误报）
    - category_navigation（委托 category_navigation_detector）

    并委托 interactive_element_classifier 做 HTML 模式补充检测。

interactive_element_classifier
    ③ 补充：版本切换、语言切换、cookie 弹窗、软登录提示（login_prompt）、
    验证码、Tab 面板、侧边栏导航、客户端路由（client_side_router）等。

category_navigation_detector
    ③ 子模块：从可见文本 + 内链样本提取顶部分类/频道导航（课程平台、新闻站等）。

version_signal_util
    ⑤ 辅助降噪：剥离 script/style，过滤 api-v1 类误报，只认 v2.4 文档版本格式。

version_url_extractor
    ⑤ 从渲染后 HTML 链接提取版本 URL 前缀事实（如 ``/docs/v2.4/``）。

probe_action_planner
    ⑤ 汇总版本 URL 事实；可推断 ``/docs/{lang}/{version}/`` 前缀。
    不输出 suggested_actions，策略由 Agent 决定。

rendering_analyzer
    对比 HTTP 与浏览器渲染正文字符数，判定渲染模式与空壳风险。

url_signals_analyzer
    纯 URL 字符串分析：路径是否含版本段、语言段。

site_type_scorer
    ④ 对齐 prompts.yaml 八种站点类型打分（技术文档、新闻博客、电商、SPA、
    Wiki、政府机构、API 文档、社交论坛），只打分不替 Agent 定 site_type。

crawl_implications_engine
    将探针结果压缩为短标签索引，供 Agent 速览，例如：

    - needs_browser_rendering / shell_risk_high
    - ask_user_for_credentials / login_form_fields_detected
    - category_navigation_detected / ask_user_for_crawl_scope
    - site_search_available / version_url_patterns_discovered
    - client_side_routing_detected / may_need_expand_hook

    细节以 interactive_elements / controls / page_structure 为准。

③ 交互归类分工
----------------
interaction_classifier 走两条互补路径：

1. **控件驱动**（更准）：password input → login_gate；搜索 input → search_box；
   select 控件 → filter_panel。
2. **HTML 模式驱动**（补充）：版本/语言/cookie/软登录/验证码/路由等，
   由 interactive_element_classifier 检测；若控件已识别 login_gate 则跳过重复。

典型输出字段（RenderedPageProbeVo）
------------------------------------
::

    rendering              mode, shell_risk, needs_browser, content_ratio
    page_structure         markdown_chars, internal_link_count, link_samples, ...
    controls               [{ tag, control_type, selector, text, ... }]
    interactive_elements   [{ category, confidence, evidence, fields, options, ... }]
    site_type_candidates   [{ site_type, score, signals }]
    version_url_patterns   [{ version_label, url_prefix, sample_href, evidence }]
    crawl_implications     短标签列表（索引用，非最终策略）

刻意不做什么
------------
- 不预生成 hooks 或 suggested_actions
- 不替 Agent 定 site_type / strategy_config
- 不做 per-site 硬编码规则

阅读顺序建议
------------
1. rendered_page_probe_service.py  — 看编排顺序
2. interaction_classifier.py       — 看交互检测主逻辑
3. crawl_implications_engine.py    — 看 Agent 速览标签如何映射
4. 其余模块按需跳转
"""
